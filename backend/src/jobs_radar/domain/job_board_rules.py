"""Pure rules for the pre-filter of job-board postings (ADR-049.4, research R-00173).

A job board publishes far more postings than the owner can use, and each stored posting costs a
local-model extraction. These rules decide, from what the board itself states, whether a posting is
worth storing. They never judge fit: a posting whose eligibility is not stated is kept and left to
the later location judgement (ADR-021), so the pre-filter only removes what is clearly outside.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from jobs_radar.domain.regions import expand_regions


class Reach(StrEnum):
    """Who may take a posting, as far as the board says."""

    WORLDWIDE = "worldwide"
    COUNTRIES = "countries"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Eligibility:
    """Where the person doing the job may be located; ``countries`` is set only for COUNTRIES."""

    reach: Reach
    countries: frozenset[str] = frozenset()


WORLDWIDE = Eligibility(Reach.WORLDWIDE)
UNKNOWN = Eligibility(Reach.UNKNOWN)


def eligibility_from_regions(regions: Sequence[str]) -> Eligibility:
    """Turn region names (country codes, ``Europe``, ``Anywhere`` ...) into an eligibility."""
    countries, recognised = expand_regions(regions)
    if not recognised:
        return UNKNOWN
    if countries is None:
        return WORLDWIDE
    return Eligibility(Reach.COUNTRIES, countries)


def allows_country(
    eligibility: Eligibility, country_codes: Sequence[str], *, include_worldwide: bool
) -> bool:
    """Whether a posting with ``eligibility`` passes the owner's country filter."""
    if eligibility.reach is Reach.UNKNOWN:
        return True
    if eligibility.reach is Reach.WORLDWIDE:
        return include_worldwide
    return bool(eligibility.countries & set(country_codes))


# Keyword families per technology area; matched on whole words after hyphens become spaces.
_AREAS: dict[str, re.Pattern[str]] = {
    "software": re.compile(
        r"\b(software|developer|programmer|engineer|engineering|backend|frontend|full stack|"
        r"fullstack|mobile|android|ios|web|qa|sdet|architect|react|python|java|javascript|"
        r"typescript|golang|rust|node|php|ruby|kotlin|swift)\b",
        re.IGNORECASE,
    ),
    "data": re.compile(
        r"\b(data|analytics|analytic|machine learning|ml|ai|artificial intelligence|bi|etl|"
        r"scientist|llm)\b",
        re.IGNORECASE,
    ),
    "devops": re.compile(
        r"\b(devops|sre|site reliability|infrastructure|cloud|kubernetes|platform|sysadmin|"
        r"system administrator|terraform)\b",
        re.IGNORECASE,
    ),
    "security": re.compile(
        r"\b(security|cybersecurity|infosec|appsec|pentest|pentester|pentesting)\b", re.IGNORECASE
    ),
}


def categorise(texts: Iterable[str]) -> frozenset[str]:
    """Technology areas suggested by titles, tags and category names (empty if none apply)."""
    text = " ".join(texts).replace("-", " ").replace("_", " ").replace("/", " ")
    return frozenset(area for area, pattern in _AREAS.items() if pattern.search(text))


def is_recent(posted_at: datetime | None, now: datetime, max_age_days: int) -> bool:
    """Whether a posting is no older than ``max_age_days``; an unknown date counts as recent."""
    return posted_at is None or posted_at >= now - timedelta(days=max_age_days)


def matches_terms(text: str, terms: Sequence[str]) -> bool:
    """Whether ``text`` contains any of ``terms`` (case-insensitive); no terms keeps everything."""
    if not terms:
        return True
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)
