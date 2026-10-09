"""What the worker has done and still has to do, as the owner sees it (pipeline status)."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from tests.evaluation_world import World, world
from tests.factories import unique
from tests.fake_provider import FakeProvider

from jobs_radar.db.models import JobExtraction, ProviderConnection
from jobs_radar.db.models.worker import WorkerHeartbeat
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.services.evaluation import EvaluationService
from jobs_radar.services.pipeline import PipelineService

pytestmark = pytest.mark.integration

MAX_AGE = 120
MODEL = "pipeline-model"


async def setup(
    session: AsyncSession, *, with_connection: bool = True, extraction: str | None = "succeeded"
) -> tuple[World, datetime]:
    """One job (extracted as given), a fresh worker heartbeat and a job-analysis connection."""
    now = datetime.now(UTC)
    w = await world(
        session, extracted_by=("ollama", MODEL), with_extraction=extraction == "succeeded"
    )
    if extraction in ("pending", "failed"):
        session.add(
            JobExtraction(
                job_snapshot_id=w.snapshot_id,
                status=extraction,
                provider="ollama",
                model=MODEL,
                prompt_version="extract-v1",
                taxonomy_version_id=1,
                error_class="schema_invalid" if extraction == "failed" else None,
                attempts=1,
                completed_at=now if extraction == "failed" else None,
            )
        )
    # Other tests may have committed connections or heartbeats; this transaction is rolled back.
    await session.execute(delete(ProviderConnection))
    session.add(WorkerHeartbeat(worker_name=unique("w"), started_at=now, beat_at=now))
    if with_connection:
        session.add(
            ProviderConnection(
                owner_id=LOCAL_OWNER_ID,
                provider_type="ollama",
                display_name="Local",
                endpoint_url="http://127.0.0.1:11434",
                model_id=MODEL,
                config_json={},
                use_for_jobs=True,
            )
        )
    await session.flush()
    return w, now


def service(session: AsyncSession) -> PipelineService:
    return PipelineService(session, MAX_AGE)


async def test_an_extracted_job_waits_to_be_scored_and_then_is_done(
    db_session: AsyncSession,
) -> None:
    w, now = await setup(db_session)

    before = await service(db_session).status(LOCAL_OWNER_ID, intent_id=w.intent_id, now=now)
    assert (before.analysis.total, before.analysis.done, before.analysis.waiting) == (1, 1, 0)
    assert (before.scoring.total, before.scoring.done, before.scoring.waiting) == (1, 0, 1)
    assert before.scoring.search_intent_id == w.intent_id
    assert before.ai_model == MODEL and before.state in {"working", "no_progress"}

    await EvaluationService(
        db_session, FakeProvider(responder=lambda _request: {"equivalent": [], "related": []})
    ).evaluate_pending(intent_id=w.intent_id)

    after = await service(db_session).status(LOCAL_OWNER_ID, intent_id=w.intent_id, now=now)
    assert (after.scoring.done, after.scoring.waiting) == (1, 0)
    assert after.state == "idle"
    assert after.recent.scored >= 1  # the evaluation was just created


async def test_a_job_without_a_successful_extraction_waits_for_analysis(
    db_session: AsyncSession,
) -> None:
    w, now = await setup(db_session, extraction="pending")

    status = await service(db_session).status(LOCAL_OWNER_ID, intent_id=w.intent_id, now=now)

    assert (status.analysis.total, status.analysis.done, status.analysis.waiting) == (1, 0, 1)
    assert status.scoring.total == 0  # nothing to score until it is analysed


async def test_failed_extractions_are_counted_and_the_last_reason_is_given(
    db_session: AsyncSession,
) -> None:
    w, now = await setup(db_session, extraction="failed")

    status = await service(db_session).status(LOCAL_OWNER_ID, intent_id=w.intent_id, now=now)

    assert status.analysis.failed == 1 and status.analysis.waiting == 0
    assert status.failures.last_error_class == "schema_invalid"
    assert status.failures.last_failed_at is not None


async def test_without_a_job_analysis_connection_the_state_is_no_ai(
    db_session: AsyncSession,
) -> None:
    w, now = await setup(db_session, with_connection=False)

    status = await service(db_session).status(LOCAL_OWNER_ID, intent_id=w.intent_id, now=now)

    assert status.state == "no_ai" and status.ai_model is None


async def test_a_worker_that_stopped_beating_is_reported_as_stopped(
    db_session: AsyncSession,
) -> None:
    w, now = await setup(db_session)

    status = await service(db_session).status(
        LOCAL_OWNER_ID, intent_id=w.intent_id, now=now + timedelta(hours=2)
    )

    assert status.worker.status == "stale" and status.state == "worker_stopped"


async def test_the_pipeline_status_is_served_by_the_api(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/pipeline/status")).json()

    assert body["state"] in {"no_ai", "worker_stopped", "idle", "working", "no_progress"}
    assert set(body) == {
        "state",
        "ai_model",
        "worker",
        "analysis",
        "scoring",
        "recent",
        "failures",
        "generated_at",
    }
    assert set(body["analysis"]) == {
        "total",
        "done",
        "failed",
        "waiting",
        "search_intent_id",
        "minutes_left",
    }
