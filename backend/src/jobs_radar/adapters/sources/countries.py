"""Offline country lookup for the places a job board publishes (ADR-049, GeoNames data).

Boards give a country name, a city or both ("Berlin", "Germany (Remote)"). The pre-filter needs the
country of such text; this reads it from the bundled GeoNames data without any network call. A
city name shared by several countries resolves to the most populous one, which is good enough for
a filter that only drops postings clearly outside the owner's countries.
"""

import re
from functools import lru_cache

# Names the GeoNames country list does not use, as boards commonly write them.
_ALIASES = {
    "uk": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "great britain": "GB",
    "usa": "US",
    "u.s.": "US",
    "u.s.a.": "US",
    "america": "US",
    "czech republic": "CZ",
    "turkey": "TR",
    "türkiye": "TR",
    "holland": "NL",
    "the netherlands": "NL",
    "netherlands": "NL",
    "south korea": "KR",
    "russia": "RU",
}
_SPLIT = re.compile(r"[,;/|()\[\]\N{EN DASH}\N{EM DASH}-]| or ")
_LATIN = re.compile(r"^[\N{SPACE}-\N{LATIN SMALL LETTER Y WITH STROKE}]+$")


@lru_cache(maxsize=1)
def _data() -> tuple[dict[str, str], frozenset[str], dict[str, tuple[int, str, float, float]]]:
    """Country names, ISO codes and a city index; built on first use because it is large."""
    import geonamescache  # type: ignore[import-untyped]  # the package ships no type information

    cache = geonamescache.GeonamesCache()
    names: dict[str, str] = {}
    codes: set[str] = set()
    for iso, country in cache.get_countries().items():
        names[country["name"].lower()] = iso
        codes.add(iso)
    names.update(_ALIASES)
    cities: dict[str, tuple[int, str, float, float]] = {}
    primary: set[str] = set()
    # Official names first: "Porto" must be the Portuguese city, not a bigger city that merely has
    # "Porto" among its alternate names. Alternate names only fill what no official name took.
    for use_alternates in (False, True):
        for city in cache.get_cities().values():
            population = int(city["population"])
            labels = city["alternatenames"] if use_alternates else (city["name"],)
            for label in labels:
                if len(label) > 40 or not _LATIN.match(label):
                    continue
                key = label.lower()
                if use_alternates and key in primary:
                    continue
                if key not in cities or cities[key][0] < population:
                    cities[key] = (
                        population,
                        city["countrycode"],
                        float(city["latitude"]),
                        float(city["longitude"]),
                    )
        if not use_alternates:
            primary = set(cities)
    return names, frozenset(codes), cities


def country_code(name: str) -> str | None:
    """Return the ISO 3166-1 alpha-2 code for a country name or code, or ``None``."""
    text = name.strip()
    if not text:
        return None
    names, codes, _ = _data()
    if len(text) == 2 and text.isalpha() and text.upper() in codes and text != text.lower():
        return text.upper()
    return names.get(text.lower())


def country_of_place(place: str) -> str | None:
    """Return the country of a place text, preferring a stated country over a city name."""
    tokens = [token.strip() for token in _SPLIT.split(place) if token.strip()]
    tokens = [token for token in tokens if token.lower() not in {"remote", "hybrid", "onsite"}]
    for token in reversed(tokens):
        code = country_code(token)
        if code:
            return code
    _, _, cities = _data()
    for token in tokens:
        found = cities.get(token.lower())
        if found:
            return found[1]
    return None


def place_coordinates(place: str) -> tuple[float, float] | None:
    """Return the latitude and longitude of the city named in ``place``, or ``None``.

    A country name alone is not a place: a radius around it would mean nothing.
    """
    tokens = [token.strip() for token in _SPLIT.split(place) if token.strip()]
    _, _, cities = _data()
    for token in tokens:
        if token.lower() in {"remote", "hybrid", "onsite"} or country_code(token):
            continue
        found = cities.get(token.lower())
        if found:
            return found[2], found[3]
    return None


@lru_cache(maxsize=1)
def _names_by_code() -> dict[str, str]:
    import geonamescache

    return {iso: c["name"] for iso, c in geonamescache.GeonamesCache().get_countries().items()}


def country_name(code: str) -> str | None:
    """Return the English name of an ISO 3166-1 alpha-2 code, or ``None`` if unknown."""
    return _names_by_code().get(code.upper())
