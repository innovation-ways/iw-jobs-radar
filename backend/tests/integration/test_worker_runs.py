"""The worker runs queued collection runs, recovers stuck ones and holds a single lock (T5.1, T5.3)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.factories import make_company, make_source, session_factory_for
from tests.fake_adapter import FakeAdapter, listing, make_posting

from jobs_radar.core.settings import Settings
from jobs_radar.db.models import CollectionRun, SourceConfiguration, SourceRunResult
from jobs_radar.domain.enums import LOCAL_OWNER_ID, RunStatus, SourceType
from jobs_radar.services.collection import CollectionService
from jobs_radar.worker.lock import WorkerLock
from jobs_radar.worker.main import Worker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


async def one_source(session: AsyncSession) -> SourceConfiguration:
    await session.execute(update(SourceConfiguration).values(enabled=False))
    source = await make_source(session, await make_company(session))
    source.enabled = True
    await session.flush()
    return source


async def queued_run(
    session: AsyncSession,
    trigger: str = "manual",
    status: str = "queued",
    started: datetime | None = None,
) -> CollectionRun:
    run = CollectionRun(owner_id=LOCAL_OWNER_ID, trigger=trigger, status=status, started_at=started)
    session.add(run)
    await session.flush()
    return run


def service(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    adapter: FakeAdapter,
    now: datetime = NOW,
) -> CollectionService:
    return CollectionService(
        session_factory_for(session, monkeypatch),
        {SourceType.GREENHOUSE: adapter},
        clock=lambda: now,
    )


# --- running queued runs ------------------------------------------------------------------------------


async def test_queued_runs_are_executed_oldest_first_and_only_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await db_session.execute(
        update(CollectionRun).where(CollectionRun.status == "queued").values(status="cancelled")
    )
    source = await one_source(db_session)
    first, second = await queued_run(db_session), await queued_run(db_session)
    adapter = FakeAdapter(provider=lambda _c: listing(make_posting("1")))
    svc = service(db_session, monkeypatch, adapter)
    assert await svc.run_queued() == 2
    for run in (first, second):
        await db_session.refresh(run)
        assert run.status == "succeeded"
    assert await svc.run_queued() == 0  # nothing left
    results = (
        (
            await db_session.execute(
                select(SourceRunResult).where(
                    SourceRunResult.source_configuration_id == source.source_configuration_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(results) == 2


async def test_progress_is_reported_after_each_source_so_the_worker_heartbeat_stays_fresh(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await db_session.execute(
        update(CollectionRun).where(CollectionRun.status == "queued").values(status="cancelled")
    )
    await one_source(db_session)
    await make_source(db_session, await make_company(db_session))  # a second enabled source
    await db_session.execute(update(SourceConfiguration).values(enabled=True))
    await queued_run(db_session)
    ticks: list[int] = []

    async def tick() -> None:
        ticks.append(1)

    adapter = FakeAdapter(provider=lambda _c: listing(make_posting("1")))
    count = (
        (
            await db_session.execute(
                select(SourceConfiguration).where(SourceConfiguration.enabled.is_(True))
            )
        )
        .scalars()
        .all()
    )
    await service(db_session, monkeypatch, adapter).run_queued(on_progress=tick)
    assert len(ticks) >= len(count)


# --- recovery -----------------------------------------------------------------------------------------------


async def test_runs_left_running_by_a_dead_worker_fail_as_interrupted_but_queued_runs_survive(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await db_session.execute(
        update(CollectionRun)
        .where(CollectionRun.status.in_(("queued", "running")))
        .values(status="cancelled")
    )
    await one_source(db_session)
    running = await queued_run(db_session, status="running", started=NOW - timedelta(minutes=3))
    waiting = await queued_run(db_session)
    assert await service(db_session, monkeypatch, FakeAdapter()).recover() == 1
    await db_session.refresh(running)
    await db_session.refresh(waiting)
    assert (running.status, running.error_class) == ("failed", "interrupted")
    assert waiting.status == "queued"


async def test_an_interrupted_scheduled_run_is_retried_with_a_new_run_but_a_manual_one_is_not(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await db_session.execute(
        update(CollectionRun)
        .where(CollectionRun.status.in_(("queued", "running")))
        .values(status="cancelled")
    )
    await one_source(db_session)
    await queued_run(
        db_session, trigger="scheduled", status="running", started=NOW - timedelta(minutes=3)
    )
    await service(db_session, monkeypatch, FakeAdapter()).recover()
    retry = (
        (await db_session.execute(select(CollectionRun).where(CollectionRun.status == "queued")))
        .scalars()
        .all()
    )
    assert len(retry) == 1 and retry[0].trigger == "scheduled" and retry[0].scheduled_for is None

    await db_session.execute(
        update(CollectionRun).where(CollectionRun.status == "queued").values(status="cancelled")
    )
    await queued_run(
        db_session, trigger="manual", status="running", started=NOW - timedelta(minutes=3)
    )
    await service(db_session, monkeypatch, FakeAdapter()).recover()
    assert (
        await db_session.execute(select(CollectionRun).where(CollectionRun.status == "queued"))
    ).scalars().all() == []


async def test_a_run_that_has_been_running_too_long_is_marked_stuck_and_recent_ones_are_left_alone(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await db_session.execute(
        update(CollectionRun)
        .where(CollectionRun.status.in_(("queued", "running")))
        .values(status="cancelled")
    )
    await one_source(db_session)
    old = await queued_run(db_session, status="running", started=NOW - timedelta(minutes=45))
    fresh = await queued_run(db_session, status="running", started=NOW - timedelta(minutes=5))
    assert (
        await service(db_session, monkeypatch, FakeAdapter()).fail_stuck_runs(timedelta(minutes=30))
        == 1
    )
    await db_session.refresh(old)
    await db_session.refresh(fresh)
    assert (old.status, old.error_class) == ("failed", "stuck") and fresh.status == "running"


async def test_a_failed_run_never_closes_postings(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import func

    from jobs_radar.db.models import JobPosting

    await db_session.execute(
        update(CollectionRun).where(CollectionRun.status == "queued").values(status="cancelled")
    )
    await one_source(db_session)
    await queued_run(db_session)
    adapter = FakeAdapter([listing(make_posting("1")), RuntimeError("boom")])
    svc = service(db_session, monkeypatch, adapter)
    await svc.run_queued()
    await queued_run(db_session)
    await svc.run_queued()
    closed = await db_session.scalar(
        select(func.count())
        .select_from(JobPosting)
        .where(JobPosting.external_job_id == "1", JobPosting.closed_at.is_not(None))
    )
    assert closed == 0


# --- the single-worker lock --------------------------------------------------------------------------------------


async def test_only_one_worker_holds_the_lock_and_the_next_takes_over_after_release(
    settings: Settings,
) -> None:
    engines = [create_async_engine(settings.database_url) for _ in range(2)]
    try:
        first, second = WorkerLock(engines[0]), WorkerLock(engines[1])
        assert await first.acquire() is True
        assert await first.acquire() is True  # already held: still held
        assert await second.acquire() is False
        await first.release()
        assert await second.acquire() is True
        await second.release()
    finally:
        for engine in engines:
            await engine.dispose()


async def test_a_worker_that_does_not_hold_the_lock_does_nothing(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    class Never:
        async def acquire(self) -> bool:
            return False

    worker = Worker(settings, session_factory, name="w-standby", lock=Never())  # type: ignore[arg-type]
    await worker.run_once()
    from sqlalchemy import text

    count = (
        await db_session.execute(
            text("SELECT count(*) FROM worker_heartbeat WHERE worker_name = 'w-standby'")
        )
    ).scalar_one()
    assert count == 0 and worker.beats == 0


async def test_one_iteration_creates_the_due_scheduled_run_and_executes_it(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import time

    from jobs_radar.services.schedule import ScheduleRunner, ScheduleService

    await db_session.execute(
        update(CollectionRun).where(CollectionRun.status == "queued").values(status="cancelled")
    )
    await one_source(db_session)
    clock = [NOW - timedelta(hours=3)]
    schedule = ScheduleService(db_session, clock=lambda: clock[0])
    current = await schedule.get(LOCAL_OWNER_ID)
    await schedule.update(
        LOCAL_OWNER_ID,
        run_times_local=[time(10, 0)],
        timezone="Europe/Lisbon",
        enabled=True,
        expected_version=current.setting.version,
    )
    clock[0] = NOW + timedelta(minutes=1)
    adapter = FakeAdapter(provider=lambda _c: listing(make_posting("1")))
    factory = session_factory_for(db_session, monkeypatch)
    worker = Worker(
        settings,
        session_factory,
        name="w-sched",
        collection=CollectionService(
            factory, {SourceType.GREENHOUSE: adapter}, clock=lambda: clock[0]
        ),
        schedule=ScheduleRunner(factory, clock=lambda: clock[0]),
    )
    await worker.run_once()
    runs = (
        (
            await db_session.execute(
                select(CollectionRun).where(
                    CollectionRun.trigger == "scheduled",
                    CollectionRun.scheduled_for == datetime(2026, 10, 8, 9, 0, tzinfo=UTC),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(runs) == 1 and runs[0].status == RunStatus.SUCCEEDED.value
