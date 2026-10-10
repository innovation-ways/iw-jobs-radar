"""The daily collection schedule and the runs it creates (T5.2, T5.3, ADR-031).

The owner sets a local time and a time zone; the worker creates one ``collection_run`` per
occurrence. The run is unique per ``(owner, scheduled_for)``, so it exists exactly once however
many workers poll. A run is created when its time has arrived, only if it is not older than the
catch-up window, was planned after the schedule was last saved (saving 07:30 at 10:00 does not
start a run at once), and there is something to collect.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import ConflictError, InputValidationError
from jobs_radar.db.models import CollectionRun, ScheduleSetting
from jobs_radar.domain.schedule import latest_occurrence, next_occurrence, validate_timezone
from jobs_radar.repositories.schedule import ScheduleRepository
from jobs_radar.repositories.sources import SourceRepository

Clock = Callable[[], datetime]
# A run missed because the worker was down is still started if its time was at most this long ago.
CATCH_UP_WINDOW = timedelta(hours=12)


@dataclass(frozen=True)
class ScheduleView:
    """The setting and when it runs next (``None`` while disabled)."""

    setting: ScheduleSetting
    next_run_at: datetime | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ScheduleService:
    """Use cases around the schedule. The caller owns the transaction."""

    def __init__(self, session: AsyncSession, *, clock: Clock = _utc_now) -> None:
        self._session = session
        self._schedule = ScheduleRepository(session)
        self._sources = SourceRepository(session)
        self._clock = clock

    def _view(self, setting: ScheduleSetting) -> ScheduleView:
        following = (
            next_occurrence(self._clock(), setting.run_time_local, setting.timezone)
            if setting.enabled
            else None
        )
        return ScheduleView(setting, following)

    async def get(self, owner_id: int) -> ScheduleView:
        """Return the owner's schedule, creating the default (disabled) one on first use."""
        return self._view(await self._schedule.get_or_create(owner_id))

    async def update(
        self,
        owner_id: int,
        *,
        run_time_local: time,
        timezone: str,
        enabled: bool,
        expected_version: int,
        company_recency_days: int | None = None,
    ) -> ScheduleView:
        """Change the schedule, checking the version the owner saw.

        Raises:
            InputValidationError: unknown IANA time zone.
            ConflictError: ``expected_version`` is not the current version.
        """
        try:
            validate_timezone(timezone)
        except ValueError as error:
            raise InputValidationError(str(error)) from error
        setting = await self._schedule.get_or_create(owner_id, for_update=True)
        if setting.version != expected_version:
            msg = "The schedule changed since it was loaded."
            raise ConflictError(
                msg, details={"expected": expected_version, "actual": setting.version}
            )
        setting.run_time_local = run_time_local.replace(second=0, microsecond=0)
        setting.timezone = timezone
        setting.enabled = enabled
        if company_recency_days is not None:
            setting.company_recency_days = company_recency_days
        setting.version += 1
        setting.updated_at = self._clock()
        await self._session.flush()
        return self._view(setting)

    async def create_due_run(self, owner_id: int = 1) -> CollectionRun | None:
        """Queue the scheduled run whose time has arrived, once; ``None`` when nothing is due."""
        setting = await self._schedule.get_or_create(owner_id)
        if not setting.enabled:
            return None
        now = self._clock()
        occurrence = latest_occurrence(now, setting.run_time_local, setting.timezone)
        if occurrence <= setting.updated_at or now - occurrence > CATCH_UP_WINDOW:
            return None
        if not await self._sources.list_for_owner(owner_id, only_enabled=True):
            return None
        return await self._schedule.create_scheduled_run(owner_id, occurrence)


class ScheduleRunner:
    """Queues the due scheduled run in its own transaction (used by the worker)."""

    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        *,
        clock: Clock = _utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def run(self, owner_id: int = 1) -> CollectionRun | None:
        """Create the run whose time has arrived, if any."""
        async with self._session_factory() as session:
            run = await ScheduleService(session, clock=self._clock).create_due_run(owner_id)
            await session.commit()
            return run
