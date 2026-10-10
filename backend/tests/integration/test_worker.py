"""The worker process writes heartbeats and stops cleanly (ADR-031)."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobs_radar.core.settings import Settings
from jobs_radar.worker.main import Worker

pytestmark = pytest.mark.integration


async def _heartbeat_count(session: AsyncSession) -> int:
    result = await session.execute(
        text("SELECT count(*) FROM worker_heartbeat WHERE worker_name = 'w-test'")
    )
    return int(result.scalar_one())


async def test_run_once_writes_a_fresh_heartbeat(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    await db_session.execute(text("DELETE FROM worker_heartbeat"))
    await db_session.commit()
    worker = Worker(settings, session_factory, name="w-test")
    await worker.run_once()
    row = await db_session.execute(
        text("SELECT beat_at FROM worker_heartbeat WHERE worker_name = 'w-test'")
    )
    beat_at = row.scalar_one()
    assert (datetime.now(UTC) - beat_at).total_seconds() < 5


async def test_loop_beats_repeatedly_and_stops_on_event(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    fast = settings.model_copy(update={"worker_poll_seconds": 1})
    worker = Worker(fast, session_factory, name="w-test")
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    await asyncio.sleep(1.5)
    stop.set()
    await asyncio.wait_for(task, timeout=5)  # must stop promptly, not wait a full poll interval
    assert worker.beats >= 2
    assert await _heartbeat_count(db_session) == 1


async def test_without_an_extraction_queue_the_worker_creates_no_extractions(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    """Default is No AI: collected jobs wait as "not evaluated" and nothing is queued."""
    before = (await db_session.execute(text("SELECT count(*) FROM job_extraction"))).scalar_one()
    await Worker(settings, session_factory, name="w-test").run_once()
    after = (await db_session.execute(text("SELECT count(*) FROM job_extraction"))).scalar_one()
    assert after == before


async def test_with_an_extraction_queue_one_iteration_queues_and_runs_extractions(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import update
    from tests.data import SAMPLE_JOB_DESCRIPTION, SAMPLE_JOB_TITLE, sample_extraction_output
    from tests.factories import make_company, make_posting, make_source, session_factory_for
    from tests.fake_provider import FakeProvider

    from jobs_radar.db.models import JobPosting
    from jobs_radar.services.extraction_queue import ExtractionQueue

    await db_session.execute(
        update(JobPosting).where(JobPosting.closed_at.is_(None)).values(closed_at=datetime.now(UTC))
    )
    source = await make_source(db_session, await make_company(db_session))
    _posting, snapshot = await make_posting(
        db_session, source, title=SAMPLE_JOB_TITLE, description=SAMPLE_JOB_DESCRIPTION
    )
    queue = ExtractionQueue(
        session_factory_for(db_session, monkeypatch),
        FakeProvider([sample_extraction_output()]),
        max_chars=12000,
    )
    await Worker(settings, session_factory, name="w-test", extraction=queue).run_once()

    row = (
        await db_session.execute(
            text("SELECT status FROM job_extraction WHERE job_snapshot_id = :id"),
            {"id": snapshot.job_snapshot_id},
        )
    ).scalar_one()
    assert row == "succeeded"


async def test_the_worker_scores_extracted_jobs_for_enabled_intents(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extraction, then evaluation, in one iteration: a collected job ends up scored."""
    from sqlalchemy import select
    from tests.data import sample_extraction_output
    from tests.evaluation_world import world
    from tests.factories import session_factory_for
    from tests.fake_provider import FakeProvider

    from jobs_radar.db.models import MatchEvaluation
    from jobs_radar.services.evaluation import EvaluationRunner
    from jobs_radar.services.extraction_queue import ExtractionQueue

    w = await world(db_session)

    def answer(request: object) -> object:
        # the same model extracts the job and judges skill pairs: tell them apart by the prompt
        if "Posting:" in request.user:  # type: ignore[attr-defined]
            return sample_extraction_output()
        return {"equivalent": [], "related": [], "unrelated": []}

    provider = FakeProvider(responder=answer)
    fake_factory = session_factory_for(db_session, monkeypatch)
    queue = ExtractionQueue(fake_factory, provider, max_chars=12000)
    runner = EvaluationRunner(fake_factory, provider)
    await Worker(
        settings, session_factory, name="w-test", extraction=queue, evaluation=runner
    ).run_once()

    scored = (
        (
            await db_session.execute(
                select(MatchEvaluation).where(
                    MatchEvaluation.job_snapshot_id == w.snapshot_id,
                    MatchEvaluation.intent_revision_id == w.intent_revision_id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(scored) == 1
    assert scored[0].intent_revision_id == w.intent_revision_id


async def test_the_worker_groups_postings_into_opportunities_even_without_ai(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import select, update
    from tests.factories import make_company, make_posting, make_source, session_factory_for

    from jobs_radar.db.models import JobOpportunityLink, JobPosting
    from jobs_radar.services.dedup import DedupRunner

    await db_session.execute(
        update(JobPosting).where(JobPosting.closed_at.is_(None)).values(closed_at=datetime.now(UTC))
    )
    source = await make_source(db_session, await make_company(db_session))
    posting, _snapshot = await make_posting(db_session, source)
    runner = DedupRunner(session_factory_for(db_session, monkeypatch))
    await Worker(settings, session_factory, name="w-test", dedup=runner).run_once()

    link = (
        await db_session.execute(
            select(JobOpportunityLink).where(
                JobOpportunityLink.job_posting_id == posting.job_posting_id
            )
        )
    ).scalar_one()
    assert link.state == "auto"


async def test_the_worker_judges_new_jobs_against_the_owners_directions(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select
    from tests.factories import session_factory_for
    from tests.fake_provider import FakeProvider
    from tests.integration.test_direction_evaluation import BILLING
    from tests.integration.test_direction_service import GOOD, new_job, ready

    from jobs_radar.db.models import DirectionJudgement
    from jobs_radar.services.direction_service import DirectionRunner

    w = await ready(db_session, ("Billing SME", BILLING, True))
    _, snapshot = await new_job(db_session, w, datetime.now(UTC) + timedelta(hours=1))
    provider = FakeProvider(responder=lambda request: GOOD)
    runner = DirectionRunner(
        session_factory_for(db_session, monkeypatch), provider, max_chars=12000
    )
    await Worker(settings, session_factory, name="w-test", directions=runner).run_once()
    judged = (
        (
            await db_session.execute(
                select(DirectionJudgement).where(
                    DirectionJudgement.job_snapshot_id == snapshot.job_snapshot_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert [row.level for row in judged] == ["strong"]


async def test_a_model_that_is_down_never_stops_the_worker_iteration(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime, timedelta

    from tests.factories import session_factory_for
    from tests.fake_provider import FakeProvider
    from tests.integration.test_direction_evaluation import BILLING
    from tests.integration.test_direction_service import new_job, ready

    from jobs_radar.adapters.providers.base import ProviderError
    from jobs_radar.domain.enums import ProviderErrorClass
    from jobs_radar.services.direction_service import DirectionRunner

    w = await ready(db_session, ("Billing SME", BILLING, True))
    await new_job(db_session, w, datetime.now(UTC) + timedelta(hours=1))
    provider = FakeProvider(
        responder=lambda request: ProviderError(ProviderErrorClass.UNAVAILABLE, "down")
    )
    runner = DirectionRunner(
        session_factory_for(db_session, monkeypatch), provider, max_chars=12000
    )
    worker = Worker(settings, session_factory, name="w-test", directions=runner)
    await worker.run_once()  # must not raise
    assert worker.beats >= 1
