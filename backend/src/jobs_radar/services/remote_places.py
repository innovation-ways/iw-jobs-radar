"""What a source's own remote places allow (ADR-056).

A board that writes ``India (Remote)`` or ``Remote US`` says where the work can be done from, in
a structured field the model never had to guess. This reads such places and returns the countries
they allow, so a model answer such as ``WORLD`` can be narrowed to what the source says. It only
ever limits: whenever the places do not clearly limit remote work (an office is named, a region is
unknown, a place is open to everyone) the answer is ``None``, meaning "no limit".
"""

import re
from collections.abc import Sequence

from jobs_radar.adapters.sources.countries import country_code
from jobs_radar.domain.regions import expand_regions

_REMOTE = re.compile(
    r"\b(remote|remoto|remota|home[- ]based|work from home|home office|wfh)\b", re.I
)
# Words that describe how or from where the work is done, not which country it is open to.
_FILLER = re.compile(
    r"\b(remote|remoto|remota|home[- ]based|work from home|home office|wfh|only|based|within|in|"
    r"from|hybrid|zone\s*\d+|job requisitions?)\b",
    re.I,
)
_SPLIT = re.compile(r"[,;/|()\[\]:\N{EN DASH}\N{EM DASH}-]")


def _tokens(place: str) -> list[str]:
    """Return the pieces of a place that are left after the remote wording is taken out."""
    pieces = (" ".join(_FILLER.sub(" ", piece).split()) for piece in _SPLIT.split(place))
    return [piece for piece in pieces if piece]


def _countries(token: str) -> frozenset[str] | None:
    """Return the countries a token names, or ``None`` if it is not understood or means everyone."""
    code = country_code(token)
    if code:
        return frozenset({code})
    countries, recognised = expand_regions([token])
    return countries if recognised else None


def source_remote_countries(places: Sequence[str]) -> frozenset[str] | None:
    """Return the countries the source's remote places are limited to, or ``None`` for no limit.

    Every place must be either a remote place naming countries or regions, or a bare "Remote"
    (which some adapters add and which says nothing); a named office, a region that is not
    understood or a place open to everyone means the source does not limit remote work.
    """
    allowed: set[str] = set()
    for place in (item for item in places if item.strip()):
        if not _REMOTE.search(place):
            return None  # an office (or hub): the source does not say where remote work is open
        tokens = _tokens(place)
        for token in tokens:
            found = _countries(token)
            if found is None:
                return None  # not understood, or open to everyone: the source limits nothing
            allowed |= found
    return frozenset(allowed) if allowed else None
