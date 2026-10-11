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

# Groups used by job boards that publish a region instead of a country (ADR-058).
NORTH_AMERICA = _codes("US CA MX")
LATAM = _codes("MX GT HN SV NI CR PA CU DO PR AR BO BR CL CO EC GY PY PE SR UY VE")
AMERICAS = NORTH_AMERICA | LATAM | _codes("BS BB BZ JM TT HT")
APAC = _codes("AU NZ JP KR CN HK TW SG MY TH VN PH ID IN PK BD LK NP KH LA MM MN PG FJ MO BN")
MIDDLE_EAST = _codes("AE SA IL QA KW BH OM JO LB TR IQ IR SY YE PS")
AFRICA = _codes(
    "DZ AO BJ BW BF BI CM CV CF TD KM CG CD CI DJ EG GQ ER SZ ET GA GM GH GN GW KE LS LR LY MG "
    "MW ML MR MU MA MZ NA NE NG RW ST SN SC SL SO ZA SS SD TZ TG TN UG ZM ZW"
)
EMEA = EUROPE | MIDDLE_EAST | AFRICA

_WORLD = "WORLD"
_GROUPS: dict[str, frozenset[str]] = {
    "EU": EU,
    "EEA": EEA,
    "EUROPE": EUROPE,
    "UK": frozenset({"GB"}),
    "EMEA": EMEA,
    "AMERICAS": AMERICAS,
    "NORTH AMERICA": NORTH_AMERICA,
    "LATAM": LATAM,
    "APAC": APAC,
}
_ALIASES = {
    "AMER": "AMERICAS",
    "THE AMERICAS": "AMERICAS",
    "LATIN AMERICA": "LATAM",
    "ASIA PACIFIC": "APAC",
    "EUROPE MIDDLE EAST AND AFRICA": "EMEA",
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
