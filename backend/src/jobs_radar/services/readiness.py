"""Readiness checks behind ``/readyz``: database, schema revision and worker heartbeat."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
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
    # ``stale`` means the database is behind the code: its migrations have not been applied.
    schema: ComponentStatus = ComponentStatus.UP

    @property
    def ready(self) -> bool:
        """True only when every component is up."""
        return all(part is ComponentStatus.UP for part in (self.database, self.worker, self.schema))


@lru_cache(maxsize=1)
def migration_head() -> str | None:
    """Return the newest Alembic revision shipped with the code, or ``None`` if not found.

    The migrations directory sits next to ``src`` in the repository and in the image.
    """
    directory = Path(__file__).resolve().parents[3] / "alembic"
    if not directory.is_dir():
        return None
    config = Config()
    config.set_main_option("script_location", str(directory))
    return ScriptDirectory.from_config(config).get_current_head()


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
        self,
        session_factory: async_sessionmaker[AsyncSession],
        max_heartbeat_age_seconds: int,
        expected_revision: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._max_age = max_heartbeat_age_seconds
        # ``None`` skips the schema check (the migrations directory is not available).
        self._expected_revision = expected_revision

    async def check(self) -> ReadinessReport:
        """Probe the database and the worker heartbeat; never raises."""
        try:
            async with self._session_factory() as session:
                repository = HeartbeatRepository(session)
                await repository.ping()
                beat_at = await repository.latest_beat_at()
                revision = await repository.schema_revision()
        # Intentionally broad: any failure to reach or query the database means "not ready",
        # and a readiness probe must report that rather than raise.
        except Exception:
            return ReadinessReport(ComponentStatus.DOWN, ComponentStatus.MISSING)
        worker = evaluate_worker_heartbeat(beat_at, datetime.now(UTC), self._max_age)
        behind = self._expected_revision is not None and revision != self._expected_revision
        schema = ComponentStatus.STALE if behind else ComponentStatus.UP
        return ReadinessReport(ComponentStatus.UP, worker, schema)
