"""Pre-filter for company boards: keep only postings in the owner's areas and reach (ADR-051).

A company board lists every posting of the company, most of them irrelevant to the owner and each
one costing a local-model extraction. When the owner turns filters on for a board, postings that do
not match the chosen technology areas, search terms, age or location are not stored. Unlike a job
board, a company board gives no structured eligibility, only free-text places such as
``Remote - EU`` or ``Lisbon, Portugal``, so the places are read here: a remote place is open to the
countries it names, any other place must be inside the owner's radius, and a place that cannot be
read is kept for the later judgement.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from jobs_radar.adapters.sources.base import SourcePosting
from jobs_radar.adapters.sources.countries import country_code, place_coordinates
from jobs_radar.domain.job_board_rules import (
    UNKNOWN,
    Eligibility,
    LocationCandidate,
    LocationScope,
    Reach,
    allows_location,
    eligibility_from_regions,
    is_recent,
    matches_terms,
)
from jobs_radar.domain.prefilter import PrefilterRules
from jobs_radar.schemas.source_filters import JobBoardFilters

_REMOTE = re.compile(
    r"\b(remote|remoto|remota|anywhere|worldwide|global|distributed|home office|work from home)\b",
    re.IGNORECASE,
)
# Words that say "remote" but name no country; what is left of the text names the regions.
_NOT_A_REGION = re.compile(
    r"\b(remote|remoto|remota|hybrid|distributed|home office|work from home|only|based|"
    r"within|in)\b",
    re.IGNORECASE,
)
# Words that describe how the work is done, not where; a place made only of them says nothing.
_MARKER = re.compile(r"^(hybrid|in[- ]?office|on[- ]?site|office|onsite)$", re.IGNORECASE)
_SPLIT = re.compile(r"[,;/|()\[\]\N{EN DASH}\N{EM DASH}-]")


@dataclass(frozen=True)
class FilterOutcome:
    """The postings that passed, how many were left out and whether the limit stopped the scan."""

    kept: list[SourcePosting]
    dropped: int
    truncated: bool


def _candidate(place: str) -> LocationCandidate | None:
    """Read one place text: remote work open to the regions it names, or a workplace.

    A bare country ("Spain") means the person may live there. A marker such as "Hybrid" is not a
    place and gives ``None``.
    """
    if _MARKER.match(place.strip()):
        return None
    if _REMOTE.search(place):
        regions = [
            code or token
            for token in (_NOT_A_REGION.sub("", part).strip() for part in _SPLIT.split(place))
            if token
            for code in [country_code(token)]
        ]
        return LocationCandidate(remote=True, eligibility=eligibility_from_regions(regions))
    code = country_code(place)
    if code:
        return LocationCandidate(
            remote=None, eligibility=Eligibility(Reach.COUNTRIES, frozenset({code}))
        )
    return LocationCandidate(remote=False, eligibility=UNKNOWN, place=place_coordinates(place))


def _location_ok(posting: SourcePosting, scope: LocationScope) -> bool:
    candidates = [c for place in posting.locations if (c := _candidate(place)) is not None]
    if not candidates:
        return True
    return any(allows_location(candidate, scope) for candidate in candidates)


def keep_posting(
    posting: SourcePosting,
    filters: JobBoardFilters,
    scope: LocationScope | None,
    now: datetime,
    rules: PrefilterRules | None = None,
) -> bool:
    """Whether a company-board posting passes the owner's filters for that board."""
    if rules is not None and not rules.allows(
        filters.categories, (posting.title, *posting.departments)
    ):
        return False
    if not is_recent(posting.posted_at, now, filters.max_age_days):
        return False
    text = " ".join((posting.title, *posting.departments, posting.description_text))
    if not matches_terms(text, filters.search_terms):
        return False
    return scope is None or scope.is_empty or _location_ok(posting, scope)


def apply_filters(
    postings: list[SourcePosting],
    filters: JobBoardFilters,
    scope: LocationScope | None,
    now: datetime,
    rules: PrefilterRules | None = None,
) -> FilterOutcome:
    """Filter a company board's postings, stopping at the per-run limit."""
    kept: list[SourcePosting] = []
    dropped = 0
    for posting in postings:
        if not keep_posting(posting, filters, scope, now, rules):
            dropped += 1
            continue
        if len(kept) >= filters.max_postings_per_run:
            return FilterOutcome(kept, dropped, truncated=True)
        kept.append(posting)
    return FilterOutcome(kept, dropped, truncated=False)
