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


@dataclass(frozen=True)
class LocationScope:
    """Where the owner can work, derived from the profile and the search intents (ADR-049.11).

    It is never typed into a source: ``country_codes`` are the countries of the owner's base
    location and of the regions where remote work is acceptable, ``include_worldwide`` says whether
    postings open to anyone are wanted, and ``any_country`` is set when remote work is acceptable
    from anywhere.
    """

    country_codes: frozenset[str] = frozenset()
    include_worldwide: bool = False
    any_country: bool = False

    @property
    def is_empty(self) -> bool:
        """True when nothing is known about where the owner can work."""
        return not (self.country_codes or self.include_worldwide or self.any_country)


@dataclass(frozen=True)
class LocationPreference:
    """What one enabled search intent says about location, with its profile's base country."""

    base_country: str | None
    remote_regions: Sequence[str]
    remote_acceptable: bool
    local_acceptable: bool


def derive_location_scope(preferences: Iterable[LocationPreference]) -> LocationScope:
    """Combine the location wishes of every enabled intent into one scope.

    Remote work contributes the countries of its eligible regions (and worldwide postings); hybrid
    or on-site work contributes the base country. An intent that rejects an arrangement
    contributes nothing for it.
    """
    countries: set[str] = set()
    worldwide = any_country = False
    for preference in preferences:
        if preference.remote_acceptable:
            worldwide = True
            expanded, recognised = expand_regions(preference.remote_regions)
            if recognised and expanded is None:
                any_country = True
            elif expanded:
                countries |= expanded
        if preference.local_acceptable and preference.base_country:
            countries.add(preference.base_country.upper())
    return LocationScope(frozenset(countries), worldwide, any_country)


def allows_country(eligibility: Eligibility, scope: LocationScope) -> bool:
    """Whether a posting with ``eligibility`` passes the owner's location scope."""
    if eligibility.reach is Reach.UNKNOWN:
        return True
    if eligibility.reach is Reach.WORLDWIDE:
        return scope.include_worldwide
    return scope.any_country or bool(eligibility.countries & scope.country_codes)


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
