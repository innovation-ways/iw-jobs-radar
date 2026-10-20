"""Analysing open jobs again with the current prompt, only when the owner asks (ADR-080, 6c; ADR-077)."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import (
    NOW,
    make_company,
    make_inbox_item,
    make_opportunity,
    make_posting,
    make_source,
    unique,
)

from jobs_radar.core.errors import ConflictError
from jobs_radar.db.models import JobExtraction, ProviderConnection
from jobs_radar.domain.enums import (
    EXTRACTION_PROMPT_VERSION,
    LOCAL_OWNER_ID,
    InboxState,
)
from jobs_radar.repositories.extractions import ExtractionRepository
from jobs_radar.services.reextraction import ReextractionService

pytestmark = pytest.mark.integration

PROVIDER, MODEL = "ollama", "reextract-test-model"


def service_at(session: AsyncSession) -> ReextractionService:
    """The service with a fixed clock, so the tests do not age (the factories' NOW is 2026-10-08)."""
    return ReextractionService(session, clock=lambda: NOW)


async def use_a_model(session: AsyncSession, model: str | None = MODEL) -> None:
    """The owner's job-analysis connection (the only one in use for jobs)."""
    await session.execute(update(ProviderConnection).values(use_for_jobs=False))
    if model is not None:
        session.add(
            ProviderConnection(
                owner_id=LOCAL_OWNER_ID,
                provider_type=PROVIDER,
                display_name=unique("Local"),
                model_id=model,
                config_json={},
                use_for_jobs=True,
            )
        )
    await session.flush()


async def answered_job(
    session: AsyncSession,
    *,
    prompt: str = "extract-v4",
    state: InboxState = InboxState.UNREAD,
    first_seen_days_ago: int = 1,
    latency_ms: int | None = 6000,
    now: datetime = NOW,
):  # type: ignore[no-untyped-def]
    """An open job whose latest snapshot was analysed with an older, accepted prompt."""
    source = await make_source(session, await make_company(session))
    posting, snapshot = await make_posting(
        session, source, first_seen_at=now - timedelta(days=first_seen_days_ago)
    )
    session.add(
        JobExtraction(
            job_snapshot_id=snapshot.job_snapshot_id,
            status="succeeded",
            provider=PROVIDER,
            model=MODEL,
            prompt_version=prompt,
            taxonomy_version_id=1,
            attributes_json={},
            attempts=1,
            latency_ms=latency_ms,
        )
    )
    item = await make_inbox_item(session, await make_opportunity(session, posting))
    item.state = state.value
    await session.flush()
    return posting, snapshot


async def pending_rows(session: AsyncSession, snapshot_id: int) -> list[JobExtraction]:
    rows = await session.execute(
        select(JobExtraction).where(
            JobExtraction.job_snapshot_id == snapshot_id, JobExtraction.status == "pending"
        )
    )
    return list(rows.scalars())


async def test_the_preview_counts_open_jobs_analysed_with_an_older_prompt(
    db_session: AsyncSession,
) -> None:
    await use_a_model(db_session)
    await answered_job(db_session)
    await answered_job(db_session, prompt="extract-v3")
    preview = await service_at(db_session).preview(LOCAL_OWNER_ID, since_days=30)
    assert preview.candidates == 2 and preview.model == MODEL
    assert preview.minutes >= 1


async def test_queueing_adds_one_waiting_analysis_the_queue_will_claim(
    db_session: AsyncSession,
) -> None:
    """The accepted old answer would normally keep the job from being claimed again; this is the exception."""
    await use_a_model(db_session)
    _posting, snapshot = await answered_job(db_session)
    queued = await service_at(db_session).queue(LOCAL_OWNER_ID, since_days=30)
    assert queued == 1
    (row,) = await pending_rows(db_session, snapshot.job_snapshot_id)
    assert row.prompt_version == EXTRACTION_PROMPT_VERSION and row.forced is True
    claimed = await ExtractionRepository(db_session).claim_next(
        provider=PROVIDER,
        model=MODEL,
        prompt_version=EXTRACTION_PROMPT_VERSION,
        now=NOW,
        stale_before=NOW - timedelta(minutes=30),
        accepted_prompt_versions=("extract-v4", "extract-v3", "extract-v2"),
    )
    assert claimed is not None and claimed[0].job_extraction_id == row.job_extraction_id


async def test_queueing_twice_adds_nothing(db_session: AsyncSession) -> None:
    await use_a_model(db_session)
    await answered_job(db_session)
    service = service_at(db_session)
    assert await service.queue(LOCAL_OWNER_ID, since_days=30) == 1
    assert await service.queue(LOCAL_OWNER_ID, since_days=30) == 0
    assert (await service.preview(LOCAL_OWNER_ID, since_days=30)).candidates == 0


async def test_a_job_already_analysed_with_the_current_prompt_is_left_alone(
    db_session: AsyncSession,
) -> None:
    await use_a_model(db_session)
    await answered_job(db_session, prompt=EXTRACTION_PROMPT_VERSION)
    assert (await service_at(db_session).preview(LOCAL_OWNER_ID, since_days=30)).candidates == 0


@pytest.mark.parametrize("state", [InboxState.IGNORED, InboxState.ARCHIVED])
async def test_jobs_the_owner_put_away_are_not_analysed_again(
    db_session: AsyncSession, state: InboxState
) -> None:
    await use_a_model(db_session)
    await answered_job(db_session, state=state)
    assert (await service_at(db_session).preview(LOCAL_OWNER_ID, since_days=30)).candidates == 0


async def test_only_jobs_first_seen_within_the_chosen_days_count(db_session: AsyncSession) -> None:
    await use_a_model(db_session)
    await answered_job(db_session, first_seen_days_ago=5)
    await answered_job(db_session, first_seen_days_ago=45)
    service = service_at(db_session)
    assert (await service.preview(LOCAL_OWNER_ID, since_days=30)).candidates == 1
    assert (await service.preview(LOCAL_OWNER_ID, since_days=90)).candidates == 2


async def test_a_job_never_analysed_is_not_a_re_extraction(db_session: AsyncSession) -> None:
    """Those are the normal queue's work; this action is for answers that already exist."""
    await use_a_model(db_session)
    source = await make_source(db_session, await make_company(db_session))
    posting, _snapshot = await make_posting(db_session, source, first_seen_at=NOW)
    await make_inbox_item(db_session, await make_opportunity(db_session, posting))
    assert (await service_at(db_session).preview(LOCAL_OWNER_ID, since_days=30)).candidates == 0


async def test_a_closed_posting_is_not_analysed_again(db_session: AsyncSession) -> None:
    await use_a_model(db_session)
    posting, _ = await answered_job(db_session)
    posting.closed_at = NOW
    await db_session.flush()
    assert (await service_at(db_session).preview(LOCAL_OWNER_ID, since_days=30)).candidates == 0


async def test_the_time_estimate_follows_the_pace_of_recent_analyses(
    db_session: AsyncSession,
) -> None:
    await use_a_model(db_session)
    for _ in range(3):
        await answered_job(db_session, latency_ms=30_000)
    preview = await service_at(db_session).preview(LOCAL_OWNER_ID, since_days=30)
    assert preview.seconds_per_job == pytest.approx(30.0, rel=0.35)
    assert preview.minutes >= round(preview.candidates * 30 / 60) - 1


async def test_without_a_model_for_jobs_there_is_nothing_to_do(db_session: AsyncSession) -> None:
    await use_a_model(db_session, model=None)
    with pytest.raises(ConflictError):
        await service_at(db_session).preview(LOCAL_OWNER_ID, since_days=30)
    with pytest.raises(ConflictError):
        await service_at(db_session).queue(LOCAL_OWNER_ID, since_days=30)


async def test_the_api_previews_and_queues(
    isolated_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await use_a_model(db_session)
    await answered_job(db_session, now=datetime.now(UTC))  # the API uses the real clock
    preview = await isolated_client.get("/api/v1/pipeline/re-extraction", params={"since_days": 30})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["candidates"] == 1 and body["model"] == MODEL and body["minutes"] >= 1
    queued = await isolated_client.post("/api/v1/pipeline/re-extraction", json={"since_days": 30})
    assert queued.status_code == 200 and queued.json() == {"queued": 1}
    again = await isolated_client.get("/api/v1/pipeline/re-extraction", params={"since_days": 30})
    assert again.json()["candidates"] == 0


async def test_the_api_refuses_a_missing_model_and_a_silly_window(
    isolated_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await use_a_model(db_session, model=None)
    assert (await isolated_client.get("/api/v1/pipeline/re-extraction")).status_code == 409
    assert (
        await isolated_client.get("/api/v1/pipeline/re-extraction", params={"since_days": 0})
    ).status_code == 422
    assert (
        await isolated_client.post("/api/v1/pipeline/re-extraction", json={"since_days": 4000})
    ).status_code == 422
