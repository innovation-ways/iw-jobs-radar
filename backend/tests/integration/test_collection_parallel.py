"""Sources of one run are collected at the same time, so a slow one never blocks the rest (ADR-063)."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import make_company, make_source

from jobs_radar.db.models import CollectionRun, SourceConfiguration
from jobs_radar.domain.enums import LOCAL_OWNER_ID, RunStatus, SourceOutcome
from jobs_radar.services.collection import CollectionService

pytestmark = pytest.mark.integration


def build(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, *, max_parallel: int
) -> CollectionService:
    monkeypatch.setattr(session, "commit", session.flush)

    @asynccontextmanager
    async def same_session() -> AsyncIterator[AsyncSession]:
        yield session

    factory: Callable[[], object] = same_session
    return CollectionService(factory, {}, max_parallel=max_parallel)  # type: ignore[arg-type]


async def enabled_sources(session: AsyncSession, count: int) -> list[int]:
    await session.execute(update(SourceConfiguration).values(enabled=False))
    ids = []
    for _ in range(count):
        source = await make_source(session, await make_company(session))
        source.enabled = True
        ids.append(source.source_configuration_id)
    await session.flush()
    return ids


async def execute(service: CollectionService, **kwargs: object) -> CollectionRun:
    run = await service.request_run(LOCAL_OWNER_ID)
    await service.execute_run(run.collection_run_id, **kwargs)  # type: ignore[arg-type]
    return run


async def test_sources_are_collected_at_the_same_time(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await enabled_sources(db_session, 4)
    service = build(db_session, monkeypatch, max_parallel=8)
    started = 0
    all_started = asyncio.Event()

    async def process(run_id: int, source_id: int) -> SourceOutcome:
        nonlocal started
        started += 1
        if started == 4:
            all_started.set()
        # One after the other this never ends: a source only starts when the previous one is done,
        # so a slow source would hold back every source behind it.
        await asyncio.wait_for(all_started.wait(), timeout=5)
        return SourceOutcome.SUCCESS

    monkeypatch.setattr(service, "_process_source", process)
    run = await execute(service)
    await db_session.refresh(run)
    assert run.status == RunStatus.SUCCEEDED.value and started == 4


async def test_no_more_than_the_limit_run_at_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await enabled_sources(db_session, 6)
    service = build(db_session, monkeypatch, max_parallel=2)
    active = peak = 0

    async def process(run_id: int, source_id: int) -> SourceOutcome:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return SourceOutcome.SUCCESS

    monkeypatch.setattr(service, "_process_source", process)
    await execute(service)
    assert peak == 2


async def test_a_source_that_crashes_is_a_failure_and_the_run_carries_on(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = await enabled_sources(db_session, 3)
    service = build(db_session, monkeypatch, max_parallel=8)
    done: list[int] = []

    async def process(run_id: int, source_id: int) -> SourceOutcome:
        if source_id == ids[0]:
            msg = "boom"
            raise RuntimeError(msg)
        done.append(source_id)
        return SourceOutcome.SUCCESS

    monkeypatch.setattr(service, "_process_source", process)
    run = await execute(service)
    await db_session.refresh(run)
    assert sorted(done) == sorted(ids[1:])
    assert run.status == RunStatus.PARTIAL.value


async def test_progress_is_reported_once_per_source(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await enabled_sources(db_session, 5)
    service = build(db_session, monkeypatch, max_parallel=3)
    ticks = 0

    async def process(run_id: int, source_id: int) -> SourceOutcome:
        return SourceOutcome.SUCCESS

    async def progress() -> None:
        nonlocal ticks
        ticks += 1

    monkeypatch.setattr(service, "_process_source", process)
    await execute(service, on_progress=progress)
    assert ticks == 5
