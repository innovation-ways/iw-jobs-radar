"""Temporary in-process runner for collection runs (document 14, T2.5).

Until the worker process exists (T5) the API starts queued runs as background tasks of its own
event loop. Tasks are tracked so tests can wait for them and shutdown can cancel them; a task
that raises is logged and never takes the API down.
"""

import asyncio
import logging
from collections.abc import Awaitable

logger = logging.getLogger(__name__)


class RunExecutor:
    """Keeps strong references to background run tasks until they finish."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def submit(self, work: Awaitable[None]) -> None:
        """Start ``work`` in the background."""

        async def guarded() -> None:
            try:
                await work
            except asyncio.CancelledError:
                raise
            # Intentionally broad: a background run must never crash the API process.
            except Exception:
                logger.exception("collection_run_crashed")

        task = asyncio.get_running_loop().create_task(guarded())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def wait_idle(self) -> None:
        """Wait until every submitted run has finished."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def shutdown(self) -> None:
        """Cancel runs still in flight (they are marked interrupted on the next start)."""
        for task in list(self._tasks):
            task.cancel()
        await self.wait_idle()
