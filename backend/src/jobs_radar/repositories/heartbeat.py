"""Data access for worker heartbeats and the database liveness probe."""

from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models.worker import WorkerHeartbeat


class HeartbeatRepository:
    """Reads and writes the ``worker_heartbeat`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ping(self) -> None:
        """Run a trivial query; raises if the database is unreachable."""
        await self._session.execute(text("SELECT 1"))

    async def latest_beat_at(self) -> datetime | None:
        """Return the most recent heartbeat time across workers, or ``None`` if there is none."""
        result = await self._session.execute(select(func.max(WorkerHeartbeat.beat_at)))
        return result.scalar_one_or_none()

    async def beat(self, worker_name: str, started_at: datetime, now: datetime) -> None:
        """Insert or refresh the heartbeat of ``worker_name``."""
        statement = insert(WorkerHeartbeat).values(
            worker_name=worker_name, started_at=started_at, beat_at=now
        )
        statement = statement.on_conflict_do_update(
            index_elements=[WorkerHeartbeat.worker_name],
            set_={"started_at": started_at, "beat_at": now},
        )
        await self._session.execute(statement)
        await self._session.commit()
