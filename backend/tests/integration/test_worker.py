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
