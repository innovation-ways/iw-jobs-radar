"""Readiness checks behind ``/readyz``: database reachability and worker heartbeat age."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobs_radar.repositories.heartbeat import HeartbeatRepository


class ComponentStatus(StrEnum):
    """State of one readiness component."""

    UP = "up"
    DOWN = "down"
    STALE = "stale"
    MISSING = "missing"


@dataclass(frozen=True)
class ReadinessReport:
    """Result of a readiness check."""

    database: ComponentStatus
    worker: ComponentStatus

    @property
    def ready(self) -> bool:
        """True only when every component is up."""
        return self.database is ComponentStatus.UP and self.worker is ComponentStatus.UP


def evaluate_worker_heartbeat(
    beat_at: datetime | None, now: datetime, max_age_seconds: int
) -> ComponentStatus:
    """Classify the worker from its latest heartbeat: ``missing``, ``stale`` or ``up``."""
    if beat_at is None:
        return ComponentStatus.MISSING
    age = (now - beat_at).total_seconds()
    return ComponentStatus.UP if age <= max_age_seconds else ComponentStatus.STALE


class ReadinessService:
    """Checks the dependencies that must work for the application to be useful."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], max_heartbeat_age_seconds: int
    ) -> None:
        self._session_factory = session_factory
        self._max_age = max_heartbeat_age_seconds

    async def check(self) -> ReadinessReport:
        """Probe the database and the worker heartbeat; never raises."""
        try:
            async with self._session_factory() as session:
                repository = HeartbeatRepository(session)
                await repository.ping()
                beat_at = await repository.latest_beat_at()
        # Intentionally broad: any failure to reach or query the database means "not ready",
        # and a readiness probe must report that rather than raise.
        except Exception:
            return ReadinessReport(ComponentStatus.DOWN, ComponentStatus.MISSING)
        worker = evaluate_worker_heartbeat(beat_at, datetime.now(UTC), self._max_age)
        return ReadinessReport(ComponentStatus.UP, worker)
