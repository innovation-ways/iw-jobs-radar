"""The worker process: a single asyncio loop that polls the database (ADR-017, ADR-031).

In this foundation task the loop only records a heartbeat. Collection, scheduling and
extraction are added to ``run_once`` by later tasks.
"""

import asyncio
import contextlib
import signal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobs_radar.core.logging import configure_logging
from jobs_radar.core.settings import Settings, get_settings
from jobs_radar.db.session import build_engine, build_session_factory
from jobs_radar.services.heartbeat import HeartbeatService

logger = structlog.get_logger()


class Worker:
    """Polling loop that keeps the worker's heartbeat fresh and runs queued work."""

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        name: str = "worker",
    ) -> None:
        self._settings = settings
        self._heartbeat = HeartbeatService(session_factory, name)
        self.beats = 0

    async def run_once(self) -> None:
        """Perform one iteration of the loop."""
        await self._heartbeat.beat()
        self.beats += 1

    async def run(self, stop: asyncio.Event) -> None:
        """Loop until ``stop`` is set; a stop request interrupts the wait between iterations."""
        logger.info("worker_started", poll_seconds=self._settings.worker_poll_seconds)
        while not stop.is_set():
            try:
                await self.run_once()
            # Intentionally broad: one failing iteration (for example a database outage) must not
            # kill the worker; it is logged and retried on the next poll.
            except Exception:
                logger.exception("worker_iteration_failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self._settings.worker_poll_seconds)
        logger.info("worker_stopped")


async def main() -> None:
    """Entry point: run the worker until SIGINT or SIGTERM."""
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = build_engine(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    try:
        await Worker(settings, build_session_factory(engine)).run(stop)
    finally:
        await engine.dispose()
