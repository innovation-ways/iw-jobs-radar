"""A worker that only reports that it is alive (make demo-worker).

The demo database holds fictional sources, so the real worker must never run against it: it would
try to collect them. The screens still show "worker up" only while a heartbeat is fresh, so this
process keeps the heartbeat fresh and does nothing else.
"""

import asyncio
import contextlib
import signal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobs_radar.core.settings import get_settings
from jobs_radar.db.session import build_engine, build_session_factory
from jobs_radar.services.heartbeat import HeartbeatService
from jobs_radar.tools.demo_seed import check_environment


async def beat_until(
    session_factory: async_sessionmaker[AsyncSession], stop: asyncio.Event, *, interval: float
) -> int:
    """Beat every ``interval`` seconds until ``stop`` is set; return how many beats were written."""
    heartbeat = HeartbeatService(session_factory, "worker")
    beats = 0
    while not stop.is_set():
        await heartbeat.beat()
        beats += 1
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)
    return beats


async def main() -> None:
    """Entry point: beat until SIGINT or SIGTERM (only against the demo database)."""
    settings = get_settings()
    check_environment(settings)
    engine = build_engine(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    try:
        await beat_until(build_session_factory(engine), stop, interval=15.0)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
