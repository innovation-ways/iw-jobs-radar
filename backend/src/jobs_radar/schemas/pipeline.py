"""API contract for the pipeline status: what the worker has done and still has to do."""

from datetime import datetime
from typing import Literal

from jobs_radar.schemas.common import StrictModel

PipelineStateName = Literal[
    "no_ai", "worker_stopped", "idle", "working", "no_progress", "collecting"
]
WorkerStatusName = Literal["up", "stale", "missing"]


class QueueRead(StrictModel):
    """Progress through one stage for the jobs that are still open."""

    total: int
    done: int
    failed: int
    waiting: int
    search_intent_id: int | None = None
    minutes_left: int | None = None


class WorkerRead(StrictModel):
    """The worker process as seen through its heartbeat."""

    status: WorkerStatusName
    last_beat_at: datetime | None


class RecentRead(StrictModel):
    """Work finished in the recent window, from which the pace and the time left are derived."""

    window_minutes: int
    analysed: int
    scored: int
    analysed_per_minute: float
    scored_per_minute: float


class FailuresRead(StrictModel):
    """Open jobs whose analysis failed, with the reason of the latest failure."""

    count: int
    last_error_class: str | None
    last_failed_at: datetime | None


class PipelineStatusRead(StrictModel):
    """Everything the interface needs to show whether analysis and scoring are keeping up."""

    state: PipelineStateName
    ai_model: str | None
    worker: WorkerRead
    analysis: QueueRead
    scoring: QueueRead
    recent: RecentRead
    failures: FailuresRead
    generated_at: datetime
