"""Collecting sources: ingest, change detection, lifecycle and failure isolation (T2.3, T2.4)."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import unique
from tests.fake_adapter import FakeAdapter, listing, make_posting, not_modified

from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.core.errors import (
    ConflictError,
    DependencyUnavailableError,
    InputValidationError,
    NotFoundError,
)
from jobs_radar.db.models import (
    CollectionRun,
    Company,
    JobChangeEvent,
    JobPosting,
    JobSnapshot,
    SourceConfiguration,
    SourceRunResult,
)
from jobs_radar.domain.enums import (
    LOCAL_OWNER_ID,
    RunStatus,
    RunTrigger,
    SourceErrorClass,
    SourceOutcome,
    SourceType,
)
from jobs_radar.schemas.job import NormalisedJob
from jobs_radar.services.collection import CollectionService
from jobs_radar.services.sources import SourceService

pytestmark = pytest.mark.integration

T0 = datetime(2026, 10, 8, 7, 30, tzinfo=UTC)


class Clock:
    """A controllable clock: each ``tick`` moves time forward one day."""

    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def tick(self) -> None:
        self.now += timedelta(days=1)


@pytest.fixture
def clock() -> Clock:
    return Clock()


def factory_for(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> Callable[[], object]:
    """A session factory that always yields the test's session and never really commits."""
    monkeypatch.setattr(session, "commit", session.flush)

    @asynccontextmanager
    async def same_session() -> AsyncIterator[AsyncSession]:
        yield session

    return same_session


async def new_source(
    session: AsyncSession, adapter: FakeAdapter, *, name: str | None = None, enabled: bool = True
) -> SourceConfiguration:
    service = SourceService(session, {SourceType.GREENHOUSE: adapter})
    adapter.board = (
        type(adapter.board)(name=name or unique("Synthetic Co"), postings_count=1)
        if not isinstance(adapter.board, Exception)
        else adapter.board
    )
    return await service.add(
        owner_id=LOCAL_OWNER_ID,
        source_type=SourceType.GREENHOUSE,
        identifier=unique("board"),
        enabled=enabled,
    )


def collection(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, adapter: FakeAdapter, clock: Clock
) -> CollectionService:
    return CollectionService(
        factory_for(session, monkeypatch), {SourceType.GREENHOUSE: adapter}, clock=clock
    )  # type: ignore[arg-type]


async def run_all(
    service: CollectionService, session: AsyncSession, clock: Clock, source_id: int | None = None
) -> CollectionRun:
    run = await service.request_run(LOCAL_OWNER_ID, source_configuration_id=source_id)
    await service.execute_run(run.collection_run_id)
    await session.refresh(run)
    return run


async def result_of(
    session: AsyncSession, run: CollectionRun, source: SourceConfiguration
) -> SourceRunResult:
    return (
        await session.execute(
            select(SourceRunResult).where(
                SourceRunResult.collection_run_id == run.collection_run_id,
                SourceRunResult.source_configuration_id == source.source_configuration_id,
            )
        )
    ).scalar_one()


async def postings_of(session: AsyncSession, source: SourceConfiguration) -> dict[str, JobPosting]:
    rows = await session.execute(
        select(JobPosting).where(
            JobPosting.source_configuration_id == source.source_configuration_id
        )
    )
    return {p.external_job_id: p for p in rows.scalars()}


async def count(session: AsyncSession, model: type, **filters: object) -> int:
    statement = select(func.count()).select_from(model)
    for column, value in filters.items():
        statement = statement.where(getattr(model, column) == value)
    return int((await session.execute(statement)).scalar_one())


# --- adding a source -------------------------------------------------------------------------------------------


async def test_adding_a_board_validates_it_and_creates_the_company(
    db_session: AsyncSession,
) -> None:
    adapter = FakeAdapter()
    source = await new_source(db_session, adapter, name="Acme Robotics")
    assert source.source_type == "greenhouse"
    assert source.display_name == "Acme Robotics"
    assert source.url == f"https://boards.example.test/v1/boards/{source.external_identifier}/jobs"
    assert source.enabled is True
    assert source.etag is None
    company = await db_session.get(Company, source.company_id)
    assert company is not None and company.canonical_name == "Acme Robotics"
    assert company.name_normalised == "acme robotics"


async def test_two_boards_of_the_same_company_share_it(db_session: AsyncSession) -> None:
    name = unique("Shared Co")
    first = await new_source(db_session, FakeAdapter(), name=name)
    second = await new_source(db_session, FakeAdapter(), name=name.upper())  # case does not matter
    assert first.company_id == second.company_id


async def test_the_same_board_cannot_be_added_twice(db_session: AsyncSession) -> None:
    adapter = FakeAdapter()
    service = SourceService(db_session, {SourceType.GREENHOUSE: adapter})
    await service.add(
        owner_id=LOCAL_OWNER_ID, source_type=SourceType.GREENHOUSE, identifier="dup-board-x"
    )
    with pytest.raises(ConflictError):
        await service.add(
            owner_id=LOCAL_OWNER_ID, source_type=SourceType.GREENHOUSE, identifier="dup-board-x"
        )


@pytest.mark.parametrize(
    ("failure", "expected_error", "expected_class"),
    [
        (
            SourceError(SourceErrorClass.NOT_FOUND, "The board was not found.", http_status=404),
            InputValidationError,
            "not_found",
        ),
        (
            SourceError(SourceErrorClass.CONFIGURATION, "Bad token."),
            InputValidationError,
            "configuration",
        ),
        (SourceError(SourceErrorClass.TIMEOUT, "Too slow."), DependencyUnavailableError, "timeout"),
        (
            SourceError(SourceErrorClass.RATE_LIMITED, "Slow down."),
            DependencyUnavailableError,
            "rate_limited",
        ),
    ],
)
async def test_a_board_that_cannot_be_validated_is_not_saved(
    db_session: AsyncSession,
    failure: SourceError,
    expected_error: type[Exception],
    expected_class: str,
) -> None:
    service = SourceService(db_session, {SourceType.GREENHOUSE: FakeAdapter(board=failure)})
    before = await count(db_session, SourceConfiguration)
    with pytest.raises(expected_error) as error:
        await service.add(
            owner_id=LOCAL_OWNER_ID, source_type=SourceType.GREENHOUSE, identifier="whatever"
        )
    assert error.value.details["error_class"] == expected_class  # type: ignore[attr-defined]
    assert await count(db_session, SourceConfiguration) == before


async def test_validate_without_saving(db_session: AsyncSession) -> None:
    service = SourceService(db_session, {SourceType.GREENHOUSE: FakeAdapter(board=None)})
    info = await service.validate(SourceType.GREENHOUSE, "any-token")
    assert info.name == "Synthetic Co"


async def test_updating_a_source_checks_the_version(db_session: AsyncSession) -> None:
    source = await new_source(db_session, FakeAdapter())
    service = SourceService(db_session, {SourceType.GREENHOUSE: FakeAdapter()})
    updated = await service.update(
        LOCAL_OWNER_ID,
        source.source_configuration_id,
        expected_version=1,
        enabled=False,
        rate_limit_per_minute=3,
    )
    assert (updated.enabled, updated.rate_limit_per_minute, updated.version) == (False, 3, 2)
    with pytest.raises(ConflictError):
        await service.update(
            LOCAL_OWNER_ID, source.source_configuration_id, expected_version=1, enabled=True
        )
    with pytest.raises(NotFoundError):
        await service.update(LOCAL_OWNER_ID, 987654321, expected_version=1, enabled=True)


# --- first collection -----------------------------------------------------------------------------------------


async def test_the_first_run_stores_postings_snapshots_and_counts(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter(
        [listing(make_posting("1"), make_posting("2", title="Platform Engineer"))]
    )
    source = await new_source(db_session, adapter)
    run = await run_all(
        collection(db_session, monkeypatch, adapter, clock),
        db_session,
        clock,
        source.source_configuration_id,
    )

    assert run.status == RunStatus.SUCCEEDED.value
    assert run.started_at == T0 and run.finished_at is not None
    result = await result_of(db_session, run, source)
    assert result.outcome == SourceOutcome.SUCCESS.value
    assert (
        result.collected_count,
        result.new_count,
        result.updated_count,
        result.deduplicated_count,
        result.closed_count,
    ) == (2, 2, 0, 0, 0)
    assert result.http_status == 200 and result.error_class is None

    postings = await postings_of(db_session, source)
    assert set(postings) == {"1", "2"}
    assert (
        postings["1"].first_seen_at == T0
        and postings["1"].last_seen_at == T0
        and postings["1"].closed_at is None
    )
    assert postings["1"].company_id == source.company_id
    assert await count(db_session, JobSnapshot, job_posting_id=postings["1"].job_posting_id) == 1
    await db_session.refresh(source)
    assert source.etag == 'W/"v1"'


async def test_the_stored_snapshot_is_a_valid_normalised_job_with_unknown_facts(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter(
        [listing(make_posting("1", locations=("Remote - EU", "Lisbon, Portugal")))]
    )
    source = await new_source(db_session, adapter)
    await run_all(
        collection(db_session, monkeypatch, adapter, clock),
        db_session,
        clock,
        source.source_configuration_id,
    )
    posting = (await postings_of(db_session, source))["1"]
    snapshot = (
        await db_session.execute(
            select(JobSnapshot).where(JobSnapshot.job_posting_id == posting.job_posting_id)
        )
    ).scalar_one()

    job = NormalisedJob.model_validate(snapshot.normalised_json)
    assert job.title == "Senior AI Solutions Engineer"
    assert job.description_text == "Design and evaluate LLM-powered features."
    assert [location.raw for location in job.work_arrangement.locations] == [
        "Remote - EU",
        "Lisbon, Portugal",
    ]
    assert job.employer.company_id == source.company_id
    assert job.source.external_job_id == "1" and job.source.source_type.value == "greenhouse"
    # nothing the source does not state is guessed (ADR-005)
    assert job.compensation.status == "unknown"
    assert job.work_arrangement.mode.status == "unknown"
    assert job.seniority.status == "unknown" and job.sectors.status == "unknown"
    assert snapshot.raw_payload_json == {"id": "1", "title": "Senior AI Solutions Engineer"}


# --- later collections ----------------------------------------------------------------------------------------


async def test_an_identical_second_run_adds_nothing_but_refreshes_last_seen(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter([listing(make_posting("1")), listing(make_posting("1"))])
    source = await new_source(db_session, adapter)
    service = collection(db_session, monkeypatch, adapter, clock)
    await run_all(service, db_session, clock, source.source_configuration_id)
    clock.tick()
    run2 = await run_all(service, db_session, clock, source.source_configuration_id)

    result = await result_of(db_session, run2, source)
    assert (result.new_count, result.updated_count, result.deduplicated_count) == (0, 0, 1)
    posting = (await postings_of(db_session, source))["1"]
    assert posting.first_seen_at == T0
    assert posting.last_seen_at == T0 + timedelta(days=1)
    assert await count(db_session, JobSnapshot, job_posting_id=posting.job_posting_id) == 1
    assert await count(db_session, JobChangeEvent, job_posting_id=posting.job_posting_id) == 0


async def test_cosmetic_changes_create_no_snapshot_and_no_event(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter(
        [
            listing(make_posting("1", locations=("Remote - EU", "Lisbon, Portugal"))),
            listing(
                make_posting(
                    "1",
                    title="  Senior  AI Solutions Engineer ",
                    description="Design and evaluate   LLM-powered\nfeatures.",
                    locations=("Lisbon, Portugal", "Remote - EU"),
                    url="https://jobs.example.test/1?gh_src=newsletter&utm_source=x",
                )
            ),
        ]
    )
    source = await new_source(db_session, adapter)
    service = collection(db_session, monkeypatch, adapter, clock)
    await run_all(service, db_session, clock, source.source_configuration_id)
    clock.tick()
    run2 = await run_all(service, db_session, clock, source.source_configuration_id)

    assert (await result_of(db_session, run2, source)).updated_count == 0
    posting = (await postings_of(db_session, source))["1"]
    assert await count(db_session, JobSnapshot, job_posting_id=posting.job_posting_id) == 1
    assert await count(db_session, JobChangeEvent, job_posting_id=posting.job_posting_id) == 0


async def test_a_material_change_adds_a_snapshot_and_a_change_event(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter(
        [
            listing(make_posting("1")),
            listing(
                make_posting(
                    "1",
                    title="Staff AI Solutions Engineer",
                    description="A much changed description.",
                )
            ),
        ]
    )
    source = await new_source(db_session, adapter)
    service = collection(db_session, monkeypatch, adapter, clock)
    await run_all(service, db_session, clock, source.source_configuration_id)
    clock.tick()
    run2 = await run_all(service, db_session, clock, source.source_configuration_id)

    result = await result_of(db_session, run2, source)
    assert (result.new_count, result.updated_count, result.deduplicated_count) == (0, 1, 0)
    posting = (await postings_of(db_session, source))["1"]
    assert posting.title == "Staff AI Solutions Engineer"
    snapshots = (
        (
            await db_session.execute(
                select(JobSnapshot)
                .where(JobSnapshot.job_posting_id == posting.job_posting_id)
                .order_by(JobSnapshot.job_snapshot_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(snapshots) == 2
    event = (
        await db_session.execute(
            select(JobChangeEvent).where(JobChangeEvent.job_posting_id == posting.job_posting_id)
        )
    ).scalar_one()
    assert event.changed_fields == ["title", "description"]
    assert event.is_material is True
    assert (event.from_job_snapshot_id, event.to_job_snapshot_id) == (
        snapshots[0].job_snapshot_id,
        snapshots[1].job_snapshot_id,
    )
    assert posting.current_content_hash == snapshots[1].content_hash


async def test_a_not_modified_answer_refreshes_every_open_posting(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter([listing(make_posting("1"), make_posting("2")), not_modified()])
    source = await new_source(db_session, adapter)
    service = collection(db_session, monkeypatch, adapter, clock)
    await run_all(service, db_session, clock, source.source_configuration_id)
    clock.tick()
    run2 = await run_all(service, db_session, clock, source.source_configuration_id)

    assert adapter.checkpoints[1].etag == 'W/"v1"'  # the stored ETag was sent
    result = await result_of(db_session, run2, source)
    assert result.outcome == SourceOutcome.NOT_MODIFIED.value
    assert (
        result.collected_count,
        result.new_count,
        result.updated_count,
        result.deduplicated_count,
        result.closed_count,
    ) == (2, 0, 0, 2, 0)
    assert result.http_status == 304
    for posting in (await postings_of(db_session, source)).values():
        assert posting.last_seen_at == T0 + timedelta(days=1) and posting.closed_at is None


# --- lifecycle ----------------------------------------------------------------------------------------------------


async def test_a_posting_is_closed_only_after_two_consecutive_successful_runs_without_it(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter(
        [
            listing(make_posting("1"), make_posting("2")),
            listing(make_posting("1")),
            listing(make_posting("1")),
        ]
    )
    source = await new_source(db_session, adapter)
    service = collection(db_session, monkeypatch, adapter, clock)
    await run_all(service, db_session, clock, source.source_configuration_id)

    clock.tick()
    run2 = await run_all(
        service, db_session, clock, source.source_configuration_id
    )  # first run without "2"
    assert (await postings_of(db_session, source))["2"].closed_at is None
    assert (await result_of(db_session, run2, source)).closed_count == 0

    clock.tick()
    run3 = await run_all(
        service, db_session, clock, source.source_configuration_id
    )  # second run without "2"
    postings = await postings_of(db_session, source)
    assert postings["2"].closed_at == T0 + timedelta(days=2)
    assert postings["1"].closed_at is None
    assert (await result_of(db_session, run3, source)).closed_count == 1


async def test_a_failed_run_never_closes_anything_and_does_not_count_as_a_miss(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    boom = SourceError(
        SourceErrorClass.SERVER_ERROR,
        "The source reported an error; try again later.",
        http_status=503,
    )
    adapter = FakeAdapter(
        [listing(make_posting("1"), make_posting("2")), boom, boom, listing(make_posting("1"))]
    )
    source = await new_source(db_session, adapter)
    service = collection(db_session, monkeypatch, adapter, clock)
    await run_all(service, db_session, clock, source.source_configuration_id)
    for _ in range(2):  # two failed runs in a row
        clock.tick()
        failed = await run_all(service, db_session, clock, source.source_configuration_id)
        assert failed.status == RunStatus.FAILED.value
    assert (await postings_of(db_session, source))["2"].closed_at is None

    clock.tick()
    await run_all(
        service, db_session, clock, source.source_configuration_id
    )  # first successful run without "2"
    assert (await postings_of(db_session, source))[
        "2"
    ].closed_at is None  # failures did not count as misses


async def test_a_posting_that_reappears_is_reopened(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter(
        [
            listing(make_posting("1"), make_posting("2")),
            listing(make_posting("1")),
            listing(make_posting("1")),
            listing(make_posting("1"), make_posting("2")),
        ]
    )
    source = await new_source(db_session, adapter)
    service = collection(db_session, monkeypatch, adapter, clock)
    for _ in range(3):
        await run_all(service, db_session, clock, source.source_configuration_id)
        clock.tick()
    assert (await postings_of(db_session, source))["2"].closed_at is not None

    run4 = await run_all(service, db_session, clock, source.source_configuration_id)
    assert (await postings_of(db_session, source))["2"].closed_at is None
    assert (await result_of(db_session, run4, source)).updated_count == 1  # a reopened job is news


# --- failures ----------------------------------------------------------------------------------------------------------


async def test_a_failed_source_records_a_classified_safe_error(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    error = SourceError(
        SourceErrorClass.NOT_FOUND,
        "The board was not found. Check the board token.",
        http_status=404,
    )
    adapter = FakeAdapter([error])
    source = await new_source(db_session, adapter)
    run = await run_all(
        collection(db_session, monkeypatch, adapter, clock),
        db_session,
        clock,
        source.source_configuration_id,
    )
    result = await result_of(db_session, run, source)
    assert result.outcome == SourceOutcome.FAILED.value
    assert (result.error_class, result.http_status) == ("not_found", 404)
    assert result.error_message == "The board was not found. Check the board token."
    assert result.collected_count == 0
    assert run.status == RunStatus.FAILED.value


async def test_an_unexpected_adapter_crash_is_recorded_without_leaking_details(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter([RuntimeError("secret internal detail 10.0.0.9")])
    source = await new_source(db_session, adapter)
    run = await run_all(
        collection(db_session, monkeypatch, adapter, clock),
        db_session,
        clock,
        source.source_configuration_id,
    )
    result = await result_of(db_session, run, source)
    assert result.outcome == "failed" and result.error_class == "unknown"
    assert "secret" not in (result.error_message or "") and "10.0.0.9" not in (
        result.error_message or ""
    )


async def test_one_failing_source_does_not_stop_the_others(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    # An isolated owner-wide "all sources" run only sees enabled sources, so disable every other one first.
    await db_session.execute(SourceConfiguration.__table__.update().values(enabled=False))
    good_adapter = FakeAdapter([listing(make_posting("9"))])
    bad = await new_source(db_session, good_adapter)
    good = await new_source(db_session, good_adapter)

    def provider(checkpoint):  # type: ignore[no-untyped-def]
        if checkpoint.identifier == bad.external_identifier:
            return SourceError(SourceErrorClass.TIMEOUT, "The source did not answer in time.")
        return listing(make_posting("9"))

    good_adapter.provider = provider
    service = collection(db_session, monkeypatch, good_adapter, clock)
    run = await run_all(service, db_session, clock)  # all enabled sources

    assert run.status == RunStatus.PARTIAL.value
    assert (await result_of(db_session, run, bad)).outcome == "failed"
    assert (await result_of(db_session, run, good)).outcome == "success"
    assert set(await postings_of(db_session, good)) == {"9"}
    assert await postings_of(db_session, bad) == {}


async def test_disabled_sources_are_skipped_by_an_all_run_but_can_be_run_manually(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    await db_session.execute(SourceConfiguration.__table__.update().values(enabled=False))
    adapter = FakeAdapter(provider=lambda _checkpoint: listing(make_posting("1")))
    enabled = await new_source(db_session, adapter)
    disabled = await new_source(db_session, adapter, enabled=False)
    service = collection(db_session, monkeypatch, adapter, clock)

    run = await run_all(service, db_session, clock)
    assert await count(db_session, SourceRunResult, collection_run_id=run.collection_run_id) == 1
    assert await postings_of(db_session, disabled) == {}
    assert set(await postings_of(db_session, enabled)) == {"1"}

    manual = await run_all(service, db_session, clock, disabled.source_configuration_id)
    assert manual.trigger == RunTrigger.MANUAL.value
    assert manual.source_configuration_id == disabled.source_configuration_id
    assert set(await postings_of(db_session, disabled)) == {"1"}


async def test_requesting_a_run_with_no_enabled_sources_is_a_validation_error(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    await db_session.execute(SourceConfiguration.__table__.update().values(enabled=False))
    service = collection(db_session, monkeypatch, FakeAdapter(), clock)
    with pytest.raises(InputValidationError, match="enabled"):
        await service.request_run(LOCAL_OWNER_ID)
    with pytest.raises(NotFoundError):
        await service.request_run(LOCAL_OWNER_ID, source_configuration_id=987654321)


async def test_a_run_is_executed_once_only(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter([listing(make_posting("1"))])
    source = await new_source(db_session, adapter)
    service = collection(db_session, monkeypatch, adapter, clock)
    run = await run_all(service, db_session, clock, source.source_configuration_id)
    await service.execute_run(run.collection_run_id)  # already finished: ignored
    assert await count(db_session, SourceRunResult, collection_run_id=run.collection_run_id) == 1
    assert len(adapter.checkpoints) == 1


async def test_runs_left_running_by_a_previous_process_fail_but_queued_runs_still_run(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    stale_queued = CollectionRun(owner_id=LOCAL_OWNER_ID, trigger="manual", status="queued")
    stale_running = CollectionRun(owner_id=LOCAL_OWNER_ID, trigger="manual", status="running")
    done = CollectionRun(owner_id=LOCAL_OWNER_ID, trigger="manual", status="succeeded")
    db_session.add_all([stale_queued, stale_running, done])
    await db_session.flush()
    service = collection(db_session, monkeypatch, FakeAdapter(), clock)
    assert await service.recover() >= 1
    await db_session.refresh(stale_running)
    assert (stale_running.status, stale_running.error_class) == ("failed", "interrupted")
    await db_session.refresh(stale_queued)
    await db_session.refresh(done)
    assert stale_queued.status == "queued" and done.status == "succeeded"


# --- status listing ------------------------------------------------------------------------------------------------------


async def test_the_source_listing_shows_the_last_result_and_open_postings(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    adapter = FakeAdapter([listing(make_posting("1"), make_posting("2"))])
    source = await new_source(db_session, adapter)
    never = await new_source(db_session, FakeAdapter())
    await run_all(
        collection(db_session, monkeypatch, adapter, clock),
        db_session,
        clock,
        source.source_configuration_id,
    )

    rows = {
        row.source.source_configuration_id: row
        for row in await SourceService(db_session, {}).list_with_status(LOCAL_OWNER_ID)
    }
    ran = rows[source.source_configuration_id]
    assert ran.open_postings == 2
    assert ran.last_result is not None and ran.last_result.new_count == 2
    assert ran.company_name == source.display_name
    idle = rows[never.source_configuration_id]
    assert idle.last_result is None and idle.open_postings == 0


async def test_a_material_change_moves_the_inbox_item_to_updated_unread_but_cosmetic_ones_do_not(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    from jobs_radar.db.models import JobInboxItem, JobOpportunityLink
    from jobs_radar.domain.enums import InboxAction
    from jobs_radar.services.dedup import DedupService
    from jobs_radar.services.inbox import InboxService

    adapter = FakeAdapter(
        [
            listing(make_posting("1")),
            listing(make_posting("1", title="  Senior  AI Solutions Engineer ")),  # cosmetic
            listing(make_posting("1", title="Staff AI Solutions Engineer")),  # material
        ]
    )
    source = await new_source(db_session, adapter)
    service = collection(db_session, monkeypatch, adapter, clock)
    await run_all(service, db_session, clock, source.source_configuration_id)
    posting = (await postings_of(db_session, source))["1"]
    await DedupService(db_session).link_posting(posting.job_posting_id)
    inbox = InboxService(db_session)
    await inbox.surface_new(LOCAL_OWNER_ID)
    item = (
        await db_session.execute(
            select(JobInboxItem)
            .join(
                JobOpportunityLink,
                JobOpportunityLink.job_opportunity_id == JobInboxItem.job_opportunity_id,
            )
            .where(JobOpportunityLink.job_posting_id == posting.job_posting_id)
        )
    ).scalar_one()
    await inbox.act(
        LOCAL_OWNER_ID, item.job_inbox_item_id, InboxAction.OPEN, expected_version=item.version
    )

    clock.tick()
    await run_all(service, db_session, clock, source.source_configuration_id)  # cosmetic
    await db_session.refresh(item)
    assert item.state == "read"

    clock.tick()
    await run_all(service, db_session, clock, source.source_configuration_id)  # material
    await db_session.refresh(item)
    assert item.state == "updated_unread"
