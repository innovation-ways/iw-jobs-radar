"""Pure maths of the market trends (T7.5, document 13 section 11, ADR-022).

Weeks start on Monday (UTC). Trend charts mislead when the set of sources or the intent changes,
so the helpers expose *shares*, the *history that exists* (a longer period stays locked until the
data covers it) and *change points* where a series stops being comparable.
"""

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise


@dataclass(frozen=True)
class Period:
    """A selectable period of the Trends screen."""

    key: str
    weeks: int
    available: bool = False


PERIODS = (Period("4w", 4), Period("12w", 12), Period("6m", 26))


def week_start(moment: datetime) -> date:
    """Return the Monday (UTC date) of the week containing ``moment``."""
    utc = moment.astimezone(UTC)
    return (utc - timedelta(days=utc.weekday())).date()


def week_range(first: date, last: date) -> list[date]:
    """Return every week start from ``first`` to ``last`` inclusive."""
    weeks = []
    current = first
    while current <= last:
        weeks.append(current)
        current += timedelta(weeks=1)
    return weeks


def is_open_at(first_seen: datetime, closed_at: datetime | None, moment: datetime) -> bool:
    """Whether an opportunity was open at ``moment``: seen by then and not yet closed."""
    return first_seen <= moment and (closed_at is None or closed_at > moment)


def share(count: int, total: int) -> float | None:
    """Return ``count / total``, or ``None`` when there is no total to compare with."""
    return count / total if total else None


def change_between(values: Sequence[float | None]) -> float | None:
    """Return the difference between the last and the first known value of a series."""
    known = [v for v in values if v is not None]
    if len(known) < 2:
        return 0.0 if len(known) == 1 or not values else None
    return known[-1] - known[0]


def period_availability(available_weeks: int) -> list[Period]:
    """Return the periods, each marked available when the history covers it."""
    return [Period(p.key, p.weeks, available_weeks >= p.weeks) for p in PERIODS]


def change_points(series: Sequence[tuple[date, object]]) -> list[date]:
    """Return the weeks whose value differs from the previous week's."""
    return [current[0] for previous, current in pairwise(series) if current[1] != previous[1]]


def source_set_hash(source_ids: Iterable[int]) -> str:
    """Return a stable hash of a set of source ids (marks weeks that are not comparable)."""
    text = ",".join(str(i) for i in sorted(set(source_ids)))
    return hashlib.sha256(text.encode()).hexdigest()
