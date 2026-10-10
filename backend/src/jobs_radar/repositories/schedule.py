"""Data access for the daily schedule setting and scheduled runs (ADR-031)."""

from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import CollectionRun, ScheduleSetting
from jobs_radar.domain.enums import RunStatus, RunTrigger

DEFAULT_RUN_TIME = time(7, 30)
DEFAULT_TIMEZONE = "Europe/Lisbon"
DEFAULT_COMPANY_RECENCY_DAYS = 30


class ScheduleRepository:
    """Reads and writes ``schedule_setting`` and creates scheduled ``collection_run`` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, owner_id: int, *, for_update: bool = False) -> ScheduleSetting:
        """Return the owner's setting, creating the default (disabled) one on first use."""
        statement = select(ScheduleSetting).where(ScheduleSetting.owner_id == owner_id)
        if for_update:
            statement = statement.with_for_update()
        setting = (await self._session.execute(statement)).scalar_one_or_none()
        if setting is None:
            await self._session.execute(
                insert(ScheduleSetting)
                .values(
                    owner_id=owner_id,
                    run_time_local=DEFAULT_RUN_TIME,
                    timezone=DEFAULT_TIMEZONE,
                    enabled=False,
                )
                .on_conflict_do_nothing(index_elements=["owner_id"])
            )
            setting = (await self._session.execute(statement)).scalar_one()
        return setting

    async def company_recency_days(self, owner_id: int) -> int:
        """Return the owner's recency limit for company views (the default if never saved)."""
        days = (
            await self._session.execute(
                select(ScheduleSetting.company_recency_days).where(
                    ScheduleSetting.owner_id == owner_id
                )
            )
        ).scalar_one_or_none()
        return DEFAULT_COMPANY_RECENCY_DAYS if days is None else days

    async def create_scheduled_run(
        self, owner_id: int, scheduled_for: datetime
    ) -> CollectionRun | None:
        """Queue the run planned for ``scheduled_for``; ``None`` if it was already created.

        The unique ``(owner_id, scheduled_for)`` makes this safe with several workers.
        """
        run_id = (
            await self._session.execute(
                insert(CollectionRun)
                .values(
                    owner_id=owner_id,
                    trigger=RunTrigger.SCHEDULED.value,
                    status=RunStatus.QUEUED.value,
                    scheduled_for=scheduled_for,
                )
                .on_conflict_do_nothing(constraint="uq_collection_run_owner_id_scheduled_for")
                .returning(CollectionRun.collection_run_id)
            )
        ).scalar_one_or_none()
        if run_id is None:
            return None
        run = await self._session.get(CollectionRun, run_id)
        await self._session.refresh(run)  # load server-side defaults
        return run
