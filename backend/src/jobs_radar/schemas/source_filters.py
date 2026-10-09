"""Per-source filters of a job board, stored in ``source_configuration.config_json`` (ADR-049.4).

Postings that do not pass the filters are not stored, which bounds the number of local-model
extractions. The model is versioned like the other JSON payloads (``schema_version``).
"""

from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StringConstraints

from jobs_radar.schemas.common import StrictModel

# Technology areas a board entry can be narrowed to; each adapter maps its own tags onto them.
JOB_BOARD_CATEGORIES = ("software", "data", "devops", "security")

CategoryKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=40)]
# Blank terms are dropped after stripping instead of rejected, so an empty form row is harmless.
SearchTerm = Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)]


def _unique(values: list[str]) -> list[str]:
    """Drop repeated entries, keeping the first occurrence and the original order."""
    return list(dict.fromkeys(values))


def _drop_blank(values: list[str]) -> list[str]:
    return [value for value in values if value]


class JobBoardFilters(StrictModel):
    """Which postings of a job board are kept. Countries come from the profile, not from here."""

    schema_version: Literal[1] = 1
    categories: Annotated[list[CategoryKey], AfterValidator(_unique)] = Field(
        default_factory=lambda: list(JOB_BOARD_CATEGORIES), max_length=20
    )
    search_terms: Annotated[
        list[SearchTerm], AfterValidator(_drop_blank), AfterValidator(_unique)
    ] = Field(default_factory=list, max_length=20)
    max_age_days: Annotated[int, Field(ge=1, le=365)] = 30
    max_postings_per_run: Annotated[int, Field(ge=1, le=5000)] = 500
