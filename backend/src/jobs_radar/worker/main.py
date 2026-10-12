"""The worker process: a single asyncio loop that polls the database (ADR-017, ADR-031).

Only the worker holding the advisory lock does anything. Each iteration records a heartbeat,
queues the scheduled run when its time has arrived, executes queued collection runs, groups new
postings into opportunities and, when AI extraction is enabled, extracts and scores jobs for a
bounded time (keeping the heartbeat fresh).
"""

import asyncio
import contextlib
import signal
from datetime import timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobs_radar.adapters.sources.registry import build_source_adapters
from jobs_radar.core.logging import configure_logging
from jobs_radar.core.settings import Settings, get_settings
from jobs_radar.db.session import build_engine, build_session_factory
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.services.ai_settings import build_credential_box
from jobs_radar.services.collection import DEFAULT_MAX_PARALLEL_SOURCES, CollectionService
from jobs_radar.services.dedup import DedupRunner
from jobs_radar.services.direction_service import DirectionRunner
from jobs_radar.services.evaluation import EvaluationRunner
from jobs_radar.services.extraction_queue import ExtractionQueue
from jobs_radar.services.heartbeat import HeartbeatService
from jobs_radar.services.inbox import InboxRunner
from jobs_radar.services.job_summary import SummaryRunner
from jobs_radar.services.jobs_ai import JobsAiLoader
from jobs_radar.services.schedule import ScheduleRunner
from jobs_radar.services.trends import TrendRunner
from jobs_radar.worker.lock import WorkerLock

logger = structlog.get_logger()

# A run still running after this long is considered stuck and is failed (then retried if scheduled).
MAX_RUN_DURATION = timedelta(minutes=30)


class Worker:
    """Polling loop that keeps the worker's heartbeat fresh and runs queued work."""

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        name: str = "worker",
        extraction: ExtractionQueue | None = None,
        evaluation: EvaluationRunner | None = None,
        directions: DirectionRunner | None = None,
        summaries: SummaryRunner | None = None,
        dedup: DedupRunner | None = None,
        inbox: InboxRunner | None = None,
        collection: CollectionService | None = None,
        schedule: ScheduleRunner | None = None,
        lock: WorkerLock | None = None,
        jobs_ai: JobsAiLoader | None = None,
        trends: TrendRunner | None = None,
    ) -> None:
        self._settings = settings
        self._heartbeat = HeartbeatService(session_factory, name)
        self._extraction = extraction
        self._evaluation = evaluation
        self._directions = directions
        self._summaries = summaries
        self._dedup = dedup
        self._inbox = inbox
        self._collection = collection
        self._schedule = schedule
        self._lock = lock
        self._jobs_ai = jobs_ai
        self._trends = trends
        self._recovered = lock is None
        self.beats = 0

    async def _beat(self) -> None:
        await self._heartbeat.beat()
        self.beats += 1

    async def run_once(self) -> None:
        """Perform one iteration of the loop."""
        if self._lock is not None and not await self._lock.acquire():
            return  # another worker is active: stay on standby
        await self._beat()
        if self._collection is not None:
            if not self._recovered:
                # First iteration as the active worker: runs a dead worker left running fail now.
                recovered = await self._collection.recover()
                self._recovered = True
                if recovered:
                    logger.warning("runs_recovered", count=recovered)
            await self._collection.fail_stuck_runs(MAX_RUN_DURATION)
            if self._schedule is not None:
                due = await self._schedule.run()
                if due is not None:
                    logger.info("scheduled_run_queued", collection_run_id=due.collection_run_id)
            ran = await self._collection.run_queued(on_progress=self._beat)
            if ran:
                logger.info("collection_runs_executed", count=ran)
        if self._trends is not None:
            written = await self._trends.run_due(LOCAL_OWNER_ID)
            if written:
                logger.info("trends_computed", rows=written)
        extraction, evaluation, dedup = self._extraction, self._evaluation, self._dedup
        directions, summaries = self._directions, self._summaries
        if self._jobs_ai is not None:
            # The database decides (AI & privacy screen); None means No AI for jobs.
            setup = await self._jobs_ai.load()
            extraction = setup.extraction if setup else None
            evaluation = setup.evaluation if setup else None
            directions = setup.directions if setup else None
            summaries = setup.summaries if setup else None
            dedup = setup.dedup if setup else self._dedup
        if dedup is not None:
            # Grouping listings needs no AI, so it runs whether or not extraction is enabled.
            linked = await dedup.run()
            if linked:
                logger.info("opportunities_linked", linked=linked)
        if self._inbox is not None:
            surfaced = await self._inbox.run()
            if surfaced:
                logger.info("inbox_items_created", created=surfaced)
        queued = 0
        summary = None
        if extraction is not None:
            queued = await extraction.enqueue_missing()
            summary = await extraction.run_batch(
                budget_seconds=float(self._settings.worker_heartbeat_max_age_seconds) / 2,
                heartbeat=self._beat,
            )
        # While extraction has a backlog, the larger direction/summary model is left alone: it
        # competes with the extraction model for the GPU (and swaps in and out of memory), and
        # neither step feeds the score. They resume once the queue is empty.
        extraction_busy = summary is not None and summary.backlog
        if directions is not None and not extraction_busy:
            # Judging needs the job's extraction, so it follows the extraction batch and comes
            # before scoring (a job is then scored once, with its judgements); a model that is
            # down only ends this step.
            judged = await directions.run(
                budget_seconds=float(self._settings.worker_heartbeat_max_age_seconds) / 2,
                heartbeat=self._beat,
            )
            if judged:
                logger.info("directions_judged", jobs=judged)
        if summaries is not None and not extraction_busy:
            # A summary only reads the posting, so it is independent of scoring; a model that is
            # down only ends this step.
            summarised = await summaries.run(
                budget_seconds=float(self._settings.worker_heartbeat_max_age_seconds) / 2,
                heartbeat=self._beat,
            )
            if summarised:
                logger.info("summaries_written", jobs=summarised)
        if extraction is not None and summary is not None:
            scored = (
                await evaluation.run(
                    budget_seconds=float(self._settings.worker_heartbeat_max_age_seconds) / 2,
                    heartbeat=self._beat,
                )
                if evaluation is not None
                else 0
            )
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
    dedup = DedupRunner(session_factory)  # grouping works without a model
    lock = WorkerLock(engine)
    try:
        await Worker(
            settings,
            session_factory,
            dedup=dedup,
            jobs_ai=JobsAiLoader(settings, session_factory),
            trends=TrendRunner(session_factory),
            inbox=InboxRunner(session_factory, LOCAL_OWNER_ID),
            collection=CollectionService(
                session_factory,
                build_source_adapters(),
                box=build_credential_box(settings),
                max_parallel=DEFAULT_MAX_PARALLEL_SOURCES,
            ),
            schedule=ScheduleRunner(session_factory),
            lock=lock,
        ).run(stop)
    finally:
        await lock.release()
        await engine.dispose()
