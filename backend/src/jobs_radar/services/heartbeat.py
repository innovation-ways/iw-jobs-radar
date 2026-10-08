"""Records worker liveness so readiness can tell whether collection is running (ADR-031)."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobs_radar.repositories.heartbeat import HeartbeatRepository


class HeartbeatService:
    """Writes the heartbeat row of one worker process."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], name: str) -> None:
        self._session_factory = session_factory
        self._name = name
        self._started_at = datetime.now(UTC)

    async def beat(self) -> None:
        """Insert or refresh this worker's heartbeat with the current UTC time."""
        async with self._session_factory() as session:
            await HeartbeatRepository(session).beat(
                self._name, started_at=self._started_at, now=datetime.now(UTC)
            )
