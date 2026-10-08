"""The daily schedule: settings, next run and idempotent scheduled runs (T5.2, T5.3)."""

from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import make_company, make_source

from jobs_radar.core.errors import ConflictError, InputValidationError
from jobs_radar.db.models import CollectionRun, ScheduleSetting, SourceConfiguration
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.services.schedule import ScheduleService

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)  # 10:00 in Lisbon (summer time)


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


async def only_one_enabled_source(session: AsyncSession) -> None:
    """Leave exactly one enabled source so scheduled runs have something to collect."""
    await session.execute(update(SourceConfiguration).values(enabled=False))
    await make_source(session, await make_company(session))
    await session.execute(
        update(SourceConfiguration)
        .where(SourceConfiguration.enabled.is_(False))
        .where(SourceConfiguration.external_identifier.like("board-%"))
        .values(enabled=True)
    )


async def scheduled_runs(session: AsyncSession) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(CollectionRun)
                .where(CollectionRun.trigger == "scheduled")
            )
        ).scalar_one()
    )


# --- settings ----------------------------------------------------------------------------------------


async def test_the_default_schedule_is_0730_lisbon_and_disabled(db_session: AsyncSession) -> None:
    await db_session.execute(ScheduleSetting.__table__.delete())
    view = await ScheduleService(db_session).get(LOCAL_OWNER_ID)
    assert (view.setting.run_time_local, view.setting.timezone, view.setting.enabled) == (
        time(7, 30),
        "Europe/Lisbon",
        False,
    )
    assert view.next_run_at is None  # nothing runs unattended until the owner turns it on


async def test_updating_the_schedule_validates_and_reports_the_next_run(
    db_session: AsyncSession,
) -> None:
    service = ScheduleService(db_session, clock=Clock())
    await db_session.execute(ScheduleSetting.__table__.delete())
    current = await service.get(LOCAL_OWNER_ID)
    first_version = current.setting.version
    updated = await service.update(
        LOCAL_OWNER_ID,
        run_time_local=time(7, 30),
        timezone="Europe/Lisbon",
        enabled=True,
        expected_version=first_version,
    )
    assert updated.setting.enabled is True and updated.setting.version == first_version + 1
    assert updated.next_run_at == datetime(2026, 10, 9, 6, 30, tzinfo=UTC)  # 07:30 Lisbon tomorrow

    moved = await service.update(
        LOCAL_OWNER_ID,
        run_time_local=time(11, 0),
        timezone="Europe/Lisbon",
        enabled=True,
        expected_version=updated.setting.version,
    )
    assert moved.next_run_at == datetime(2026, 10, 8, 10, 0, tzinfo=UTC)  # still today


async def test_an_unknown_time_zone_or_a_stale_version_is_refused(db_session: AsyncSession) -> None:
    service = ScheduleService(db_session, clock=Clock())
    current = await service.get(LOCAL_OWNER_ID)
    seen = current.setting.version
    with pytest.raises(InputValidationError, match="time zone"):
        await service.update(
            LOCAL_OWNER_ID,
            run_time_local=time(7, 30),
            timezone="Mars/Phobos",
            enabled=True,
            expected_version=seen,
        )
    await service.update(
        LOCAL_OWNER_ID,
        run_time_local=time(8, 0),
        timezone="UTC",
        enabled=False,
        expected_version=seen,
    )
    with pytest.raises(ConflictError):
        await service.update(
            LOCAL_OWNER_ID,
            run_time_local=time(9, 0),
            timezone="UTC",
            enabled=False,
            expected_version=seen,
        )


# --- scheduled runs -------------------------------------------------------------------------------------------


async def enable_at(
    session: AsyncSession, clock: Clock, run_time: time, enabled: bool = True
) -> ScheduleService:
    service = ScheduleService(session, clock=clock)
    current = await service.get(LOCAL_OWNER_ID)
    await service.update(
        LOCAL_OWNER_ID,
        run_time_local=run_time,
        timezone="Europe/Lisbon",
        enabled=enabled,
        expected_version=current.setting.version,
    )
    return service


async def test_a_run_is_created_once_when_the_time_arrives(db_session: AsyncSession) -> None:
    await only_one_enabled_source(db_session)
    clock = Clock(NOW - timedelta(hours=3))  # 07:00 Lisbon
    service = await enable_at(db_session, clock, time(10, 0))
    assert await service.create_due_run() is None  # not yet 10:00
    before = await scheduled_runs(db_session)

    clock.now = NOW  # 10:00 Lisbon
    run = await service.create_due_run()
    assert run is not None and (run.trigger, run.status) == ("scheduled", "queued")
    assert (
        run.scheduled_for == datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
        and run.source_configuration_id is None
    )
    assert await scheduled_runs(db_session) == before + 1

    assert await service.create_due_run() is None  # the same occurrence never creates a second run
    clock.now = NOW + timedelta(minutes=14)
    assert await service.create_due_run() is None
    assert await scheduled_runs(db_session) == before + 1


async def test_the_next_day_creates_the_next_run(db_session: AsyncSession) -> None:
    await only_one_enabled_source(db_session)
    clock = Clock(NOW - timedelta(hours=3))
    service = await enable_at(db_session, clock, time(10, 0))
    clock.now = NOW
    first = await service.create_due_run()
    clock.now = NOW + timedelta(days=1)
    second = await service.create_due_run()
    assert first is not None and second is not None
    assert second.scheduled_for == first.scheduled_for + timedelta(days=1)  # type: ignore[operator]


async def test_nothing_is_created_when_disabled_or_without_enabled_sources(
    db_session: AsyncSession,
) -> None:
    await only_one_enabled_source(db_session)
    clock = Clock(NOW - timedelta(hours=3))
    off = await enable_at(db_session, clock, time(10, 0), enabled=False)
    clock.now = NOW
    assert await off.create_due_run() is None

    await enable_at(db_session, Clock(NOW - timedelta(hours=3)), time(10, 0))
    await db_session.execute(update(SourceConfiguration).values(enabled=False))
    on_now = ScheduleService(db_session, clock=Clock(NOW))
    assert await on_now.create_due_run() is None


async def test_a_time_that_already_passed_today_does_not_run_when_the_schedule_is_saved(
    db_session: AsyncSession,
) -> None:
    await only_one_enabled_source(db_session)
    clock = Clock(NOW)  # 10:00 Lisbon; the owner saves a schedule for 07:30
    service = await enable_at(db_session, clock, time(7, 30))
    assert await service.create_due_run() is None  # 07:30 is before the setting was saved


async def test_a_missed_run_is_caught_up_within_the_grace_period_only(
    db_session: AsyncSession,
) -> None:
    await only_one_enabled_source(db_session)
    saved = Clock(NOW - timedelta(days=2))
    service = await enable_at(db_session, saved, time(10, 0))
    service_late = ScheduleService(
        db_session, clock=Clock(NOW + timedelta(hours=2))
    )  # worker was down 2 h
    assert await service_late.create_due_run() is not None

    too_late = ScheduleService(
        db_session, clock=Clock(NOW + timedelta(days=1, hours=14))
    )  # 14 h after the next one
    assert await too_late.create_due_run() is None
    del service
