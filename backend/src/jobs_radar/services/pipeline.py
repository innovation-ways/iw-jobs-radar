"""The pipeline status: how much analysis and scoring is done, waiting or failed, and how fast.

The API only reads: the worker does the work. Counts follow the same rules as the worker's queues
(latest snapshot of each open posting, extracted by the connection in use), so what is shown
is what the worker will actually pick up.
"""

import math
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.domain.enums import EXTRACTION_PROMPT_VERSION
from jobs_radar.domain.matching.engine import POLICY_VERSION
from jobs_radar.repositories.evaluations import EvaluationRepository
from jobs_radar.repositories.heartbeat import HeartbeatRepository
from jobs_radar.repositories.inbox import InboxQueries
from jobs_radar.repositories.pipeline import PipelineRepository
from jobs_radar.repositories.providers import ProviderRepository
from jobs_radar.repositories.runs import RunRepository
from jobs_radar.schemas.pipeline import (
    FailuresRead,
    PipelineStateName,
    PipelineStatusRead,
    QueueRead,
    RecentRead,
    WorkerRead,
)
from jobs_radar.services.readiness import evaluate_worker_heartbeat

# Pace is measured over this window: long enough to smooth the worker's batches, short enough to
# follow a model that has slowed down or stopped.
WINDOW_MINUTES = 15


def pipeline_state(
    *,
    worker: Literal["up", "stale", "missing"] | str,
    ai_configured: bool,
    waiting: int,
    progressed: bool,
    collecting: bool = False,
) -> PipelineStateName:
    """Summarise the pipeline in one word.

    A worker that does not report comes first (nothing else can be trusted), then a missing AI
    connection. With work waiting, recent progress means ``working``; none means ``no_progress``
    (for example the model is unreachable or very slow), unless a collection is running: the worker
    is one loop that collects first and analyses what it found afterwards, so the wait is expected
    and the state is ``collecting``.
    """
    if worker != "up":
        return "worker_stopped"
    if not ai_configured:
        return "no_ai"
    if waiting == 0:
        return "idle"
    if progressed:
        return "working"
    return "collecting" if collecting else "no_progress"


def estimate_minutes_left(*, waiting: int, completed: int, window_minutes: int) -> int | None:
    """Minutes to finish ``waiting`` jobs at the pace of the window, or ``None`` if unknown."""
    if waiting <= 0 or completed <= 0:
        return None
    return math.ceil(waiting * window_minutes / completed)


class PipelineService:
    """Builds the read-only pipeline status."""

    def __init__(self, session: AsyncSession, max_heartbeat_age_seconds: int) -> None:
        self._max_age = max_heartbeat_age_seconds
        self._pipeline = PipelineRepository(session)
        self._evaluations = EvaluationRepository(session)
        self._providers = ProviderRepository(session)
        self._heartbeats = HeartbeatRepository(session)
        self._inbox = InboxQueries(session)
        self._runs = RunRepository(session)

    async def status(
        self, owner_id: int, *, intent_id: int | None = None, now: datetime | None = None
    ) -> PipelineStatusRead:
        """Return the status for the owner; ``intent_id`` defaults to the first enabled intent."""
        now = now or datetime.now(UTC)
        connection = next(
            (c for c in await self._providers.list(owner_id) if c.use_for_jobs and c.model_id),
            None,
        )
        provider = connection.provider_type if connection else None
        model = connection.model_id if connection else None

        open_jobs, analysed, failed = await self._pipeline.analysis_counts(
            provider=provider, model=model, prompt_version=EXTRACTION_PROMPT_VERSION
        )
        intent_id = intent_id or await self._inbox.default_intent_id(owner_id)
        eligible = scored = 0
        if intent_id is not None:
            filter_ = (
                (provider, model, EXTRACTION_PROMPT_VERSION)
                if provider is not None and model is not None
                else None
            )
            eligible, scored = await self._evaluations.queue_counts(
                intent_id, POLICY_VERSION, filter_
            )

        since = now - timedelta(minutes=WINDOW_MINUTES)
        recent_analysed, recent_scored = await self._pipeline.completed_since(since)
        last_error, last_failed_at = await self._pipeline.last_failure(
            provider=provider, model=model
        )
        beat_at = await self._heartbeats.latest_beat_at()
        worker = evaluate_worker_heartbeat(beat_at, now, self._max_age)

        analysis_waiting = max(open_jobs - analysed - failed, 0)
        scoring_waiting = max(eligible - scored, 0)
        return PipelineStatusRead(
            state=pipeline_state(
                worker=worker.value,
                ai_configured=connection is not None,
                waiting=analysis_waiting + scoring_waiting,
                progressed=recent_analysed + recent_scored > 0,
                collecting=await self._runs.has_running_run(owner_id),
            ),
            ai_model=model,
            worker=WorkerRead(status=worker.value, last_beat_at=beat_at),
            analysis=QueueRead(
                total=open_jobs,
                done=analysed,
                failed=failed,
                waiting=analysis_waiting,
                minutes_left=estimate_minutes_left(
                    waiting=analysis_waiting,
                    completed=recent_analysed,
                    window_minutes=WINDOW_MINUTES,
                ),
            ),
            scoring=QueueRead(
                total=eligible,
                done=scored,
                failed=0,
                waiting=scoring_waiting,
                search_intent_id=intent_id,
                minutes_left=estimate_minutes_left(
                    waiting=scoring_waiting, completed=recent_scored, window_minutes=WINDOW_MINUTES
                ),
            ),
            recent=RecentRead(
                window_minutes=WINDOW_MINUTES,
                analysed=recent_analysed,
                scored=recent_scored,
                analysed_per_minute=round(recent_analysed / WINDOW_MINUTES, 1),
                scored_per_minute=round(recent_scored / WINDOW_MINUTES, 1),
            ),
            failures=FailuresRead(
                count=failed, last_error_class=last_error, last_failed_at=last_failed_at
            ),
            generated_at=now,
        )
