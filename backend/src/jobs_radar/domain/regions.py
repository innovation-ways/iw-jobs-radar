"""Region groups for remote-work eligibility (document 13, section 7.4).

A region is an ISO 3166-1 alpha-2 country code or one of the groups ``EU``, ``EEA``, ``EUROPE``,
``UK`` and ``WORLD``. Groups are expanded to their member countries so that ``PT`` is inside
``EU`` and a job open to ``EU`` is open to someone in ``PT``. Pure functions.
"""

from collections.abc import Iterable, Sequence


def _codes(text: str) -> frozenset[str]:
    return frozenset(text.split())


EU = _codes("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE")
EEA = EU | _codes("IS LI NO")
EUROPE = EEA | _codes("GB CH AD AL BA BY MC MD ME MK RS SM UA VA XK")

_WORLD = "WORLD"
_GROUPS: dict[str, frozenset[str]] = {
    "EU": EU,
    "EEA": EEA,
    "EUROPE": EUROPE,
    "UK": frozenset({"GB"}),
}
_ALIASES = {
    "EUROPEAN UNION": "EU",
    "UNITED KINGDOM": "UK",
    "GREAT BRITAIN": "UK",
    "GB": "UK",
    "WORLDWIDE": _WORLD,
    "GLOBAL": _WORLD,
    "ANYWHERE": _WORLD,
}


def _expand(regions: Iterable[str]) -> tuple[frozenset[str] | None, bool]:
    """Return ``(countries, recognised)``; ``None`` countries means everywhere (WORLD)."""
    countries: set[str] = set()
    recognised = False
    for raw in regions:
        token = " ".join(raw.upper().split())
        token = _ALIASES.get(token, token)
        if token == _WORLD:
            return None, True
        if token in _GROUPS:
            countries |= _GROUPS[token]
            recognised = True
        elif len(token) == 2 and token.isalpha():
            countries.add(token)
            recognised = True
    return frozenset(countries), recognised


def expand_regions(regions: Iterable[str]) -> tuple[frozenset[str] | None, bool]:
    """Public form of the expansion: ``(countries, recognised)``; ``None`` countries is WORLD."""
    return _expand(regions)


def regions_intersect(job_regions: Sequence[str], user_regions: Sequence[str]) -> bool | None:
    """Whether remote work in ``job_regions`` is open to someone in ``user_regions``.

    Returns ``None`` when none of the job's regions is recognised (nothing can be concluded).
    """
    job, job_recognised = _expand(job_regions)
    if not job_recognised:
        return None
    user, _ = _expand(user_regions)
    if job is None:  # the job is open worldwide
        return user is None or bool(user)
    if user is None:
        return bool(job)
    return bool(job & user)
