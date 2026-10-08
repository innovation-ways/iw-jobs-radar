"""A PostgreSQL advisory lock that lets only one worker process be active (ADR-031).

The lock belongs to a dedicated connection held for the life of the process, so it is released
automatically if the process dies. A worker that cannot take it stays on standby and does nothing.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

# Arbitrary application-wide key of the worker lock.
WORKER_LOCK_KEY = 7_204_001


class WorkerLock:
    """Holds the single-worker advisory lock."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._connection: AsyncConnection | None = None
        self._held = False

    async def acquire(self) -> bool:
        """Try to take the lock; returns ``True`` while this process holds it."""
        if self._held:
            return True
        if self._connection is None:
            connection = await self._engine.connect()
            # Autocommit: no transaction stays open on the connection that owns the lock.
            self._connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
        result = await self._connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKER_LOCK_KEY}
        )
        self._held = bool(result.scalar_one())
        return self._held

    async def release(self) -> None:
        """Release the lock and close its connection."""
        if self._connection is not None:
            if self._held:
                await self._connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": WORKER_LOCK_KEY}
                )
            await self._connection.close()
        self._connection = None
        self._held = False
