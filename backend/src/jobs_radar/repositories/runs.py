"""Data access for collection runs and their per-source results (ADR-031)."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import CollectionRun, SourceRunResult
from jobs_radar.domain.enums import RunStatus, RunTrigger, SourceOutcome

_SUCCESSFUL = (SourceOutcome.SUCCESS.value, SourceOutcome.NOT_MODIFIED.value)


class RunRepository:
    """Reads and writes ``collection_run`` and ``source_run_result`` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, owner_id: int, trigger: RunTrigger, *, source_configuration_id: int | None = None
    ) -> CollectionRun:
        """Create a queued run; ``source_configuration_id`` limits it to one source."""
        run = CollectionRun(
            owner_id=owner_id,
            trigger=trigger.value,
            status=RunStatus.QUEUED.value,
            source_configuration_id=source_configuration_id,
        )
        self._session.add(run)
        await self._session.flush()
        await self._session.refresh(run)
        return run

    async def get(self, owner_id: int, collection_run_id: int) -> CollectionRun:
        """Return the owner's run; raises ``NotFoundError`` for unknown or foreign ids."""
        run = (
            await self._session.execute(
                select(CollectionRun).where(
                    CollectionRun.collection_run_id == collection_run_id,
                    CollectionRun.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if run is None:
            msg = "Collection run not found."
            raise NotFoundError(msg)
        return run

    async def claim(self, collection_run_id: int, started_at: datetime) -> CollectionRun | None:
        """Atomically move a queued run to running; ``None`` if it was not queued."""
        row = (
            await self._session.execute(
                update(CollectionRun)
                .where(
                    CollectionRun.collection_run_id == collection_run_id,
                    CollectionRun.status == RunStatus.QUEUED.value,
                )
                .values(
                    status=RunStatus.RUNNING.value,
                    started_at=started_at,
                    version=CollectionRun.version + 1,
                )
                .returning(CollectionRun)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        return row

    async def finish(
        self,
        run: CollectionRun,
        status: RunStatus,
        finished_at: datetime,
        *,
        error_class: str | None = None,
    ) -> None:
        """Record the final status of a run."""
        run.status = status.value
        run.finished_at = finished_at
        run.error_class = error_class
        run.version += 1
        await self._session.flush()

    async def add_result(
        self,
        *,
        collection_run_id: int,
        source_configuration_id: int,
        started_at: datetime,
        finished_at: datetime,
        outcome: SourceOutcome,
        collected_count: int = 0,
        new_count: int = 0,
        updated_count: int = 0,
        deduplicated_count: int = 0,
        closed_count: int = 0,
        http_status: int | None = None,
        error_class: str | None = None,
        error_message: str | None = None,
        duration_ms: int = 0,
    ) -> SourceRunResult:
        """Append the outcome of one source within a run."""
        result = SourceRunResult(
            collection_run_id=collection_run_id,
            source_configuration_id=source_configuration_id,
            started_at=started_at,
            finished_at=finished_at,
            outcome=outcome.value,
            collected_count=collected_count,
            new_count=new_count,
            updated_count=updated_count,
            deduplicated_count=deduplicated_count,
            closed_count=closed_count,
            http_status=http_status,
            error_class=error_class,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        self._session.add(result)
        await self._session.flush()
        return result

    async def last_successful_started_at(self, source_configuration_id: int) -> datetime | None:
        """Start time of the most recent successful (or not-modified) run of a source."""
        value = await self._session.execute(
            select(func.max(SourceRunResult.started_at)).where(
                SourceRunResult.source_configuration_id == source_configuration_id,
                SourceRunResult.outcome.in_(_SUCCESSFUL),
            )
        )
        return value.scalar_one_or_none()

    async def list_page(
        self, owner_id: int, *, limit: int, before_id: int | None
    ) -> list[CollectionRun]:
        """Return runs newest first, ``limit`` of them, older than ``before_id`` when given."""
        statement = select(CollectionRun).where(CollectionRun.owner_id == owner_id)
        if before_id is not None:
            statement = statement.where(CollectionRun.collection_run_id < before_id)
        statement = statement.order_by(CollectionRun.collection_run_id.desc()).limit(limit)
        return list((await self._session.execute(statement)).scalars())

    async def results_for(self, run_ids: Sequence[int]) -> dict[int, list[SourceRunResult]]:
        """Return the per-source results of each run."""
        if not run_ids:
            return {}
        rows = await self._session.execute(
            select(SourceRunResult)
            .where(SourceRunResult.collection_run_id.in_(run_ids))
            .order_by(SourceRunResult.source_run_result_id)
        )
        grouped: dict[int, list[SourceRunResult]] = {run_id: [] for run_id in run_ids}
        for result in rows.scalars():
            grouped[result.collection_run_id].append(result)
        return grouped

    async def fail_interrupted(self, finished_at: datetime) -> int:
        """Mark runs left queued or running by a previous process as failed (``interrupted``)."""
        result = await self._session.execute(
            update(CollectionRun)
            .where(CollectionRun.status.in_((RunStatus.QUEUED.value, RunStatus.RUNNING.value)))
            .values(
                status=RunStatus.FAILED.value, error_class="interrupted", finished_at=finished_at
            )
            .execution_options(synchronize_session="fetch")
        )
        return int(result.rowcount)  # type: ignore[attr-defined]
