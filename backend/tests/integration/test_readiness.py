"""Integration tests for readiness against a real database (ADR-031, ADR-036)."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobs_radar.core.settings import Settings
from jobs_radar.repositories.heartbeat import HeartbeatRepository
from jobs_radar.services.readiness import ComponentStatus, ReadinessService

pytestmark = pytest.mark.integration


async def _clear(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await session.execute(text("DELETE FROM worker_heartbeat"))
        await session.commit()


async def _beat(session_factory: async_sessionmaker[AsyncSession], at: datetime) -> None:
    async with session_factory() as session:
        await HeartbeatRepository(session).beat("worker-test", started_at=at, now=at)


async def test_no_heartbeat_is_reported_missing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _clear(session_factory)
    report = await ReadinessService(session_factory, 60).check()
    assert report.database is ComponentStatus.UP
    assert report.worker is ComponentStatus.MISSING
    assert not report.ready


async def test_fresh_heartbeat_is_up(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _clear(session_factory)
    await _beat(session_factory, datetime.now(UTC))
    report = await ReadinessService(session_factory, 60).check()
    assert report.ready


async def test_old_heartbeat_is_stale(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _clear(session_factory)
    await _beat(session_factory, datetime.now(UTC) - timedelta(minutes=10))
    report = await ReadinessService(session_factory, 60).check()
    assert report.worker is ComponentStatus.STALE


async def test_heartbeat_upsert_keeps_a_single_row(
    session_factory: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    await _clear(session_factory)
    now = datetime.now(UTC)
    await _beat(session_factory, now)
    await _beat(session_factory, now + timedelta(seconds=5))
    count = await db_session.execute(text("SELECT count(*) FROM worker_heartbeat"))
    assert count.scalar_one() == 1


async def test_unreachable_database_is_reported_down(settings: Settings) -> None:
    from jobs_radar.db.session import build_engine, build_session_factory

    broken = settings.model_copy(update={"db_port": 1})  # nothing listens on port 1
    engine = build_engine(broken)
    try:
        report = await ReadinessService(build_session_factory(engine), 60).check()
    finally:
        await engine.dispose()
    assert report.database is ComponentStatus.DOWN
    assert not report.ready


async def test_readyz_over_http_follows_the_heartbeat(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _clear(session_factory)
    assert (await client.get("/readyz")).status_code == 503
    await _beat(session_factory, datetime.now(UTC))
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "components": {"database": "up", "worker": "up", "schema": "up"},
    }


async def test_a_database_behind_the_code_is_reported_stale(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _clear(session_factory)
    await _beat(session_factory, datetime.now(UTC))
    service = ReadinessService(session_factory, 60, expected_revision="99999999_9999")
    report = await service.check()
    assert report.database is ComponentStatus.UP
    assert report.schema is ComponentStatus.STALE
    assert not report.ready


async def test_a_database_at_the_code_revision_is_up(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from jobs_radar.services.readiness import migration_head

    await _clear(session_factory)
    await _beat(session_factory, datetime.now(UTC))
    report = await ReadinessService(session_factory, 60, expected_revision=migration_head()).check()
    assert report.schema is ComponentStatus.UP
    assert report.ready
