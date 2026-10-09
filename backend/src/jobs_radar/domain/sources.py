"""Pure rules about job sources: category of a type and the minimum run interval (ADR-049)."""

from datetime import datetime, timedelta

from jobs_radar.domain.enums import SourceCategory, SourceType

_COMPANY_BOARDS = frozenset({SourceType.GREENHOUSE, SourceType.LEVER, SourceType.ASHBY})


def source_category(source_type: SourceType) -> SourceCategory:
    """Return the category of ``source_type``.

    Company boards (ATS) are one company per source; every other type is a job board whose
    postings belong to many companies.
    """
    if source_type in _COMPANY_BOARDS:
        return SourceCategory.COMPANY_BOARD
    return SourceCategory.JOB_BOARD


def next_run_allowed_at(
    last_attempt_finished_at: datetime | None, min_interval_minutes: int
) -> datetime | None:
    """When a board may be contacted again, or ``None`` if it was never contacted."""
    if last_attempt_finished_at is None:
        return None
    return last_attempt_finished_at + timedelta(minutes=min_interval_minutes)
