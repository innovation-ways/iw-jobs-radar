"""API contracts for the market trends (document 07, document 13 section 11)."""

from datetime import date
from typing import Literal

from jobs_radar.schemas.common import StrictModel

TermKind = Literal[
    "skill", "role_family", "sector", "work_arrangement", "seniority_level", "engagement_type"
]


class PeriodRead(StrictModel):
    """A selectable period; locked until the history covers it."""

    key: str
    weeks: int
    available: bool


class SeriesPointRead(StrictModel):
    """One week of one term."""

    week_start: date
    open_count: int
    share: float | None


class TrendRowRead(StrictModel):
    """A ranked term."""

    term_key: str
    label: str
    open_now: int
    share_now: float | None
    share_change: float | None
    count_change: int
    series: list[SeriesPointRead]


class WeekRead(StrictModel):
    """Facts about one week."""

    week_start: date
    relevant_total_open: int
    intent_revision_id: int | None


class TrendReportRead(StrictModel):
    """The Trends screen data for one term kind."""

    kind: TermKind
    search_intent_id: int
    relevance_min_score: int
    available_weeks: int
    first_week: date | None
    periods: list[PeriodRead]
    weeks: list[WeekRead]
    rows: list[TrendRowRead]
    intent_revision_changes: list[date]
    source_set_changes: list[date]
