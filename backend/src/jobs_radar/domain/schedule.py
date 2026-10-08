"""Daily schedule maths: when does the next run happen? (T5.2, ADR-031).

The owner picks a local wall-clock time and an IANA time zone, so the instant moves with daylight
saving time. A time that does not exist on a day (the clocks jump forward) runs just after the gap;
a time that happens twice (the clocks go back) runs the first time only. Pure functions.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

_ZONES = available_timezones()


def validate_timezone(name: str) -> str:
    """Return ``name`` if it is a known IANA time zone, else raise ``ValueError``."""
    if name not in _ZONES:
        msg = f"Unknown time zone: {name!r}. Use an IANA name such as Europe/Lisbon."
        raise ValueError(msg)
    return name


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(validate_timezone(name))
    except ZoneInfoNotFoundError as exc:  # pragma: no cover - available_timezones() lists it
        msg = f"Unknown time zone: {name!r}."
        raise ValueError(msg) from exc


def _at(day: date, run_time: time, zone: ZoneInfo) -> datetime:
    """Return the UTC instant of ``run_time`` on ``day`` (first occurrence; a gap moves forward)."""
    return datetime.combine(day, run_time, tzinfo=zone).astimezone(UTC)


def _check_aware(moment: datetime) -> None:
    if moment.tzinfo is None:
        msg = "The time must be timezone-aware."
        raise ValueError(msg)


def next_occurrence(after: datetime, run_time: time, timezone: str) -> datetime:
    """Return the first scheduled run strictly after ``after`` (UTC)."""
    _check_aware(after)
    zone = _zone(timezone)
    day = after.astimezone(zone).date() - timedelta(days=1)
    for _ in range(4):
        candidate = _at(day, run_time, zone)
        if candidate > after:
            return candidate
        day += timedelta(days=1)
    msg = "No next run found."  # pragma: no cover - a run exists within a day or two
    raise ValueError(msg)


def latest_occurrence(at: datetime, run_time: time, timezone: str) -> datetime:
    """Return the last scheduled run at or before ``at`` (UTC)."""
    _check_aware(at)
    zone = _zone(timezone)
    day = at.astimezone(zone).date() + timedelta(days=1)
    for _ in range(4):
        candidate = _at(day, run_time, zone)
        if candidate <= at:
            return candidate
        day -= timedelta(days=1)
    msg = "No previous run found."  # pragma: no cover
    raise ValueError(msg)
