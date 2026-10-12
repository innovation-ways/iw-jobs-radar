"""Daily schedule maths: when does the next run happen? (T5.2, ADR-031, ADR-062).

The owner picks one or more local wall-clock times and an IANA time zone, so the instants move with
daylight saving time. A time that does not exist on a day (the clocks jump forward) runs just after
the gap; a time that happens twice (the clocks go back) runs the first time only. Pure functions.
"""

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

_ZONES = available_timezones()
MAX_RUN_TIMES = 12


def normalise_run_times(run_times: Iterable[time]) -> tuple[time, ...]:
    """Return the times sorted, without seconds and without duplicates (ADR-062).

    Raises:
        ValueError: there is no time, or more than ``MAX_RUN_TIMES``.
    """
    unique = sorted({value.replace(second=0, microsecond=0, tzinfo=None) for value in run_times})
    if not unique:
        msg = "The schedule needs at least one run time."
        raise ValueError(msg)
    if len(unique) > MAX_RUN_TIMES:
        msg = f"The schedule allows at most {MAX_RUN_TIMES} run times a day."
        raise ValueError(msg)
    return tuple(unique)


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


def next_occurrence(after: datetime, run_times: Sequence[time], timezone: str) -> datetime:
    """Return the first scheduled run strictly after ``after`` (UTC), over all daily times."""
    _check_aware(after)
    _check_times(run_times)
    zone = _zone(timezone)
    day = after.astimezone(zone).date() - timedelta(days=1)
    for _ in range(4):
        # Within one day the earliest instant after ``after`` is the nearest run.
        later = [candidate for t in run_times if (candidate := _at(day, t, zone)) > after]
        if later:
            return min(later)
        day += timedelta(days=1)
    msg = "No next run found."  # pragma: no cover - a run exists within a day or two
    raise ValueError(msg)


def latest_occurrence(at: datetime, run_times: Sequence[time], timezone: str) -> datetime:
    """Return the last scheduled run at or before ``at`` (UTC), over all daily times."""
    _check_aware(at)
    _check_times(run_times)
    zone = _zone(timezone)
    day = at.astimezone(zone).date() + timedelta(days=1)
    for _ in range(4):
        earlier = [candidate for t in run_times if (candidate := _at(day, t, zone)) <= at]
        if earlier:
            return max(earlier)
        day -= timedelta(days=1)
    msg = "No previous run found."  # pragma: no cover
    raise ValueError(msg)


def _check_times(run_times: Sequence[time]) -> None:
    if not run_times:
        msg = "The schedule needs at least one run time."
        raise ValueError(msg)
