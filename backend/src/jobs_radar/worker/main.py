"""The worker process: a single asyncio loop that polls the database (ADR-017, ADR-031).

Each iteration records a heartbeat and, when AI extraction is enabled, queues and runs AI
extractions for collected jobs for a bounded time. Collection and scheduling arrive in task T5.
"""

import asyncio
import contextlib
import signal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobs_radar.adapters.providers.ollama import build_ollama_embedder, build_ollama_provider
from jobs_radar.core.logging import configure_logging
from jobs_radar.core.settings import Settings, get_settings
from jobs_radar.db.session import build_engine, build_session_factory
from jobs_radar.services.dedup import DedupRunner
from jobs_radar.services.evaluation import EvaluationRunner
from jobs_radar.services.extraction_queue import ExtractionQueue
from jobs_radar.services.heartbeat import HeartbeatService

logger = structlog.get_logger()


class Worker:
    """Polling loop that keeps the worker's heartbeat fresh and runs queued work."""

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        name: str = "worker",
        extraction: ExtractionQueue | None = None,
        evaluation: EvaluationRunner | None = None,
        dedup: DedupRunner | None = None,
    ) -> None:
        self._settings = settings
        self._heartbeat = HeartbeatService(session_factory, name)
        self._extraction = extraction
        self._evaluation = evaluation
        self._dedup = dedup
        self.beats = 0

    async def _beat(self) -> None:
        await self._heartbeat.beat()
        self.beats += 1

    async def run_once(self) -> None:
        """Perform one iteration of the loop."""
        await self._beat()
        if self._dedup is not None:
            # Grouping listings needs no AI, so it runs whether or not extraction is enabled.
            linked = await self._dedup.run()
            if linked:
                logger.info("opportunities_linked", linked=linked)
        if self._extraction is not None:
            queued = await self._extraction.enqueue_missing()
            summary = await self._extraction.run_batch(
                budget_seconds=float(self._settings.worker_heartbeat_max_age_seconds) / 2,
                heartbeat=self._beat,
            )
            scored = await self._evaluation.run() if self._evaluation is not None else 0
            if queued or scored or summary.succeeded or summary.failed or summary.stopped:
                logger.info(
                    "extraction_batch",
                    queued=queued,
                    succeeded=summary.succeeded,
                    failed=summary.failed,
                    scored=scored,
                    provider_unavailable=summary.stopped,
                )

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
    session_factory = build_session_factory(engine)
    extraction: ExtractionQueue | None = None
    evaluation: EvaluationRunner | None = None
    dedup = DedupRunner(session_factory)
    if settings.extraction_enabled:
        # AI extraction is opt-in (default is No AI); the model runs locally (ADR-035).
        provider = build_ollama_provider(settings, model=settings.extraction_model)
        extraction = ExtractionQueue(
            session_factory, provider, max_chars=settings.extraction_max_chars
        )
        evaluation = EvaluationRunner(session_factory, provider)
        dedup = DedupRunner(session_factory, build_ollama_embedder(settings))
    try:
        await Worker(
            settings, session_factory, extraction=extraction, evaluation=evaluation, dedup=dedup
        ).run(stop)
    finally:
        await engine.dispose()
