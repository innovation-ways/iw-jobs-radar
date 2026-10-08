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
