"""API contracts for the daily schedule (document 07, section 5, ADR-062)."""

from datetime import datetime, time

from pydantic import Field, field_validator

from jobs_radar.schemas.common import IanaTimezone, StrictModel


class ScheduleUpdate(StrictModel):
    """Change the schedule; ``expected_version`` is the version the client last saw."""

    # One to twelve local times of the day (ADR-062); the server stores them sorted.
    run_times_local: list[time] = Field(min_length=1, max_length=12)
    timezone: IanaTimezone
    enabled: bool
    # How old an offer may be (days since first seen) to count in the company views (ADR-053);
    # omitted keeps the stored value.
    company_recency_days: int | None = Field(default=None, ge=1, le=365)
    # Recommended jobs with a fit below this are set aside in the inbox (ADR-060); 0 turns the rule
    # off; omitted keeps the stored value.
    set_aside_below_fit: int | None = Field(default=None, ge=0, le=100)
    expected_version: int = Field(ge=1)

    @field_validator("run_times_local")
    @classmethod
    def _no_repeated_time(cls, value: list[time]) -> list[time]:
        """Reject the same minute twice: it is a mistake, not a request."""
        minutes = {item.replace(second=0, microsecond=0) for item in value}
        if len(minutes) != len(value):
            msg = "Each run time may appear only once."
            raise ValueError(msg)
        return value


class ScheduleRead(StrictModel):
    """The schedule and when it runs next (both ``null`` while disabled)."""

    run_times_local: list[str]
    timezone: str
    enabled: bool
    company_recency_days: int
    set_aside_below_fit: int
    version: int
    next_run_at: datetime | None
    next_run_local: str | None
