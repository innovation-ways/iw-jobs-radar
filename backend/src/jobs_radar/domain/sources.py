"""Pure rules about job sources: which category a source type belongs to (ADR-049)."""

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
