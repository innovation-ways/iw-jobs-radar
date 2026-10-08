"""API contracts for the daily schedule (document 07, section 5)."""

from datetime import datetime, time

from pydantic import Field

from jobs_radar.schemas.common import IanaTimezone, StrictModel


class ScheduleUpdate(StrictModel):
    """Change the schedule; ``expected_version`` is the version the client last saw."""

    run_time_local: time
    timezone: IanaTimezone
    enabled: bool
    expected_version: int = Field(ge=1)


class ScheduleRead(StrictModel):
    """The schedule and when it runs next (both ``null`` while disabled)."""

    run_time_local: str
    timezone: str
    enabled: bool
    version: int
    next_run_at: datetime | None
    next_run_local: str | None
