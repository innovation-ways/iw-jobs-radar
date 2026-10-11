"""Writing, storing and reading job summaries; the worker's selection of jobs (ADR-059)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.evaluation_world import world
from tests.factories import make_company, make_posting, make_source
from tests.fake_provider import FakeProvider

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import JobPosting, JobSnapshot, JobSummary
from jobs_radar.domain.enums import ProviderErrorClass
from jobs_radar.services.job_summary import SummaryRunner, SummaryService, SummaryUnavailable

pytestmark = pytest.mark.integration

TEXT = (
    "Acme Evaluation is hiring a senior AI engineer, fully remote within the EU. The role is on "
    "a 12-month contract.\n\nYou would design and evaluate LLM-powered features for large "
    "enterprises. The posting does not state the pay."
)
SINCE = datetime(2026, 10, 11, tzinfo=UTC)


def writing(text: str = TEXT) -> FakeProvider:
    return FakeProvider(responder=lambda request: {"summary": text})


async def rows_of(session: AsyncSession, *snapshot_ids: int) -> list[JobSummary]:
    """The summaries of these snapshots (other tests may have committed rows of their own)."""
    found = await session.execute(
        select(JobSummary)
        .where(JobSummary.job_snapshot_id.in_(snapshot_ids))
        .order_by(JobSummary.job_summary_id)
    )
    return list(found.scalars())


async def snapshot_of(session: AsyncSession, posting: JobPosting) -> int:
    return int(
        (
            await session.execute(
                select(JobSnapshot.job_snapshot_id).where(
                    JobSnapshot.job_posting_id == posting.job_posting_id
                )
            )
        ).scalar_one()
    )


async def test_a_summary_is_written_and_stored_with_its_provenance(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    provider = writing()
    result = await SummaryService(db_session, provider, max_chars=12000).summarise(
        w.posting.job_posting_id
    )
    assert (result.text, result.created) == (TEXT, True)
    (row,) = await rows_of(db_session, w.snapshot_id)
    assert (row.job_snapshot_id, row.provider, row.model, row.prompt_version, row.status) == (
        w.snapshot_id,
        "fixture",
        "fixture-model",
        "summary-v1",
        "succeeded",
    )
    # The prompt names the company, the title and the posting.
    assert "Acme Evaluation" in provider.requests[0].user


async def test_asking_again_returns_the_stored_summary_without_the_model(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    provider = writing()
    service = SummaryService(db_session, provider, max_chars=12000)
    await service.summarise(w.posting.job_posting_id)
    again = await service.summarise(w.posting.job_posting_id)
    assert (again.text, again.created) == (TEXT, False)
    assert len(provider.requests) == 1


async def test_an_unusable_answer_is_stored_as_failed_and_can_be_tried_again(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    service = SummaryService(db_session, writing("too short"), max_chars=12000)
    first = await service.summarise(w.posting.job_posting_id)
    assert (first.text, first.created) == (None, False)
    (failed,) = await rows_of(db_session, w.snapshot_id)
    assert (failed.status, failed.summary_text, failed.error_class) == (
        "failed",
        None,
        "invalid_output",
    )
    better = SummaryService(db_session, writing(), max_chars=12000)
    assert (await better.summarise(w.posting.job_posting_id)).text == TEXT


async def test_a_model_that_is_down_stores_nothing(db_session: AsyncSession) -> None:
    w = await world(db_session)
    down = FakeProvider([ProviderError(ProviderErrorClass.UNAVAILABLE, "down")])
    with pytest.raises(SummaryUnavailable):
        await SummaryService(db_session, down, max_chars=12000).summarise(w.posting.job_posting_id)
    assert await rows_of(db_session, w.snapshot_id) == []


async def test_an_unknown_posting_is_not_found(db_session: AsyncSession) -> None:
    with pytest.raises(NotFoundError):
        await SummaryService(db_session, writing(), max_chars=12000).summarise(0)


async def add_job(
    session: AsyncSession, first_seen_at: datetime, *, title: str = "Engineer"
) -> JobPosting:
    source = await make_source(session, await make_company(session, "Fresh Co"))
    posting, _ = await make_posting(session, source, title=title, first_seen_at=first_seen_at)
    return posting


async def test_the_worker_summarises_only_open_jobs_first_seen_since_the_cut_off(
    db_session: AsyncSession,
) -> None:
    await world(db_session)  # closes every other open posting
    new = await add_job(db_session, SINCE + timedelta(hours=1))
    before = await add_job(db_session, SINCE - timedelta(days=3))  # analysed before the feature
    closed = await add_job(db_session, SINCE + timedelta(hours=2))
    await db_session.execute(
        update(JobPosting)
        .where(JobPosting.job_posting_id == closed.job_posting_id)
        .values(closed_at=SINCE + timedelta(hours=3))
    )
    service = SummaryService(db_session, writing(), max_chars=12000)
    assert await service.run_pending(SINCE, limit=10) == 1
    snapshots = [await snapshot_of(db_session, p) for p in (new, before, closed)]
    (done,) = await rows_of(db_session, *snapshots)  # only the new, open job
    assert (done.job_snapshot_id, done.status) == (snapshots[0], "succeeded")
    assert await service.run_pending(SINCE, limit=10) == 0  # nothing left to do


async def test_the_worker_does_not_ask_again_for_a_job_whose_summary_failed(
    db_session: AsyncSession,
) -> None:
    await world(db_session)
    job = await add_job(db_session, SINCE + timedelta(hours=1))
    service = SummaryService(db_session, writing("too short"), max_chars=12000)
    assert await service.run_pending(SINCE, limit=10) == 1
    assert await service.run_pending(SINCE, limit=10) == 0
    rows = await rows_of(db_session, await snapshot_of(db_session, job))
    assert [row.status for row in rows] == ["failed"]


async def test_the_worker_does_the_newest_jobs_first_and_respects_the_limit(
    db_session: AsyncSession,
) -> None:
    await world(db_session)
    older = await add_job(db_session, SINCE + timedelta(hours=1), title="Older")
    newer = await add_job(db_session, SINCE + timedelta(hours=5), title="Newer")
    provider = writing()
    service = SummaryService(db_session, provider, max_chars=12000)
    assert await service.run_pending(SINCE, limit=1) == 1
    assert "Newer" in provider.requests[0].user
    assert await service.run_pending(SINCE, limit=1) == 1
    assert "Older" in provider.requests[1].user
    assert older.job_posting_id != newer.job_posting_id


async def test_a_model_that_is_down_leaves_the_jobs_waiting(db_session: AsyncSession) -> None:
    await world(db_session)
    job = await add_job(db_session, SINCE + timedelta(hours=1))
    down = FakeProvider([ProviderError(ProviderErrorClass.UNAVAILABLE, "down")])
    with pytest.raises(SummaryUnavailable):
        await SummaryService(db_session, down, max_chars=12000).run_pending(SINCE, limit=5)
    assert await rows_of(db_session, await snapshot_of(db_session, job)) == []


async def test_the_runner_commits_each_job_and_ends_quietly_when_the_model_is_down(
    db_session: AsyncSession,
) -> None:
    from contextlib import asynccontextmanager

    await world(db_session)
    await add_job(db_session, SINCE + timedelta(hours=1))

    @asynccontextmanager
    async def factory():  # type: ignore[no-untyped-def]
        yield db_session

    down = FakeProvider([ProviderError(ProviderErrorClass.UNAVAILABLE, "down")])
    runner = SummaryRunner(factory, down, max_chars=12000, since=SINCE)
    assert await runner.run() == 0  # no exception: the worker carries on


async def test_a_summary_of_an_older_prompt_does_not_count_as_written(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    snapshot_id = w.snapshot_id
    posting_id = w.posting.job_posting_id
    db_session.add(
        JobSummary(
            job_snapshot_id=snapshot_id,
            provider="fixture",
            model="fixture-model",
            prompt_version="summary-v0",
            status="succeeded",
            summary_text="An old summary written by an earlier prompt of the same model.",
        )
    )
    await db_session.flush()
    provider = writing()
    result = await SummaryService(db_session, provider, max_chars=12000).summarise(posting_id)
    assert (result.text, result.created) == (TEXT, True)
    assert len(provider.requests) == 1


async def test_many_summaries_can_be_stored_in_a_row(db_session: AsyncSession) -> None:
    """The driver prepares a statement after a few runs; the conflict rule must survive that."""
    from jobs_radar.domain.enums import SummaryStatus
    from jobs_radar.repositories.summaries import SummaryRepository

    w = await world(db_session)
    repo = SummaryRepository(db_session)
    for number in range(10):
        stored = await repo.add(
            job_snapshot_id=w.snapshot_id,
            provider="fixture",
            model=f"model-{number}",
            prompt_version="summary-v1",
            status=SummaryStatus.SUCCEEDED,
            summary_text=TEXT,
            error_class=None,
            latency_ms=5,
        )
        assert stored is True
    again = await repo.add(
        job_snapshot_id=w.snapshot_id,
        provider="fixture",
        model="model-3",
        prompt_version="summary-v1",
        status=SummaryStatus.SUCCEEDED,
        summary_text=TEXT,
        error_class=None,
        latency_ms=5,
    )
    assert again is False  # the same good summary is not stored twice
