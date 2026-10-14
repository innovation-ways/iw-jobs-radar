"""Pure rules about job sources: category of a type and the minimum run interval (ADR-049)."""

from datetime import datetime, timedelta

from jobs_radar.domain.enums import SourceCategory, SourceType

_COMPANY_BOARDS = frozenset(
    {
        SourceType.GREENHOUSE,
        SourceType.LEVER,
        SourceType.ASHBY,
        SourceType.SMARTRECRUITERS,
        SourceType.EIGHTFOLD,
        SourceType.PAGE_JSONLD,
        SourceType.PAGE_CONFIG,
    }
)


def source_category(source_type: SourceType) -> SourceCategory:
    """Return the category of ``source_type``.

    Company boards (ATS) are one company per source; every other type is a job board whose
    postings belong to many companies.
    """
    if source_type in _COMPANY_BOARDS:
        return SourceCategory.COMPANY_BOARD
    return SourceCategory.JOB_BOARD


_DEFAULT_RATE = 6
# SmartRecruiters and Eightfold need one request per posting detail, so they are allowed a faster
# pace; a company's own careers page is read one posting page at a time, at most one a second.
_RATE_OVERRIDES = {
    SourceType.SMARTRECRUITERS: 30,
    SourceType.EIGHTFOLD: 30,
    SourceType.PAGE_JSONLD: 60,
    SourceType.PAGE_CONFIG: 60,
}


def default_rate_limit(source_type: SourceType) -> int:
    """Return the default requests per minute for a company board of ``source_type``."""
    return _RATE_OVERRIDES.get(source_type, _DEFAULT_RATE)


def next_run_allowed_at(
    last_attempt_finished_at: datetime | None, min_interval_minutes: int
) -> datetime | None:
    """When a board may be contacted again, or ``None`` if it was never contacted."""
    if last_attempt_finished_at is None:
        return None
    return last_attempt_finished_at + timedelta(minutes=min_interval_minutes)
