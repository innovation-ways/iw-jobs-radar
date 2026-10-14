"""Eligibility from the free-text "where can you work from" field of a remote job board.

Remote OK and Working Nomads publish one text field (``Worldwide``, ``Europe``, ``USA``, ``Spain,
Portugal`` ...). Empty or worldwide words mean anyone; named countries and regions limit the work
to them; any part that cannot be read makes the whole text unreliable, so the posting is kept for
the later judgement instead of being dropped on a guess (ADR-049.6).
"""

import re

from jobs_radar.adapters.sources.countries import country_code
from jobs_radar.domain.job_board_rules import (
    UNKNOWN,
    WORLDWIDE,
    Eligibility,
    eligibility_from_regions,
)
from jobs_radar.domain.regions import expand_regions

_WORLD_WORDS = frozenset(
    {"worldwide", "world wide", "global", "anywhere", "anywhere in the world", "remote", "world"}
)
# Short names the offline country list writes differently.
_ALIASES = {"usa": "US", "u.s.": "US", "us": "US", "uk": "GB", "united states": "US"}
_SPLIT = re.compile(r"[,;/]|\band\b|\bor\b", re.IGNORECASE)


def _clean(part: str) -> str:
    return " ".join(part.replace("(", " ").replace(")", " ").split()).strip(" .")


def eligibility_from_place_text(text: str) -> tuple[Eligibility, tuple[str, ...]]:
    """Return ``(eligibility, places to show)`` for a board's location text."""
    cleaned = _clean(text)
    if not cleaned or cleaned.lower() in _WORLD_WORDS:
        return WORLDWIDE, ("Worldwide",)
    parts = [part for raw in _SPLIT.split(cleaned) if (part := _clean(raw))]
    if not parts:
        return UNKNOWN, (cleaned,)
    regions: list[str] = []
    for part in parts:
        lowered = part.lower()
        if lowered in _WORLD_WORDS:
            return WORLDWIDE, tuple(parts)
        code = _ALIASES.get(lowered) or country_code(part)
        candidate = code or part
        # One unreadable part makes the list unreliable: keep the posting for the judgement.
        if not expand_regions([candidate])[1]:
            return UNKNOWN, tuple(parts)
        regions.append(candidate)
    return eligibility_from_regions(regions), tuple(parts)
