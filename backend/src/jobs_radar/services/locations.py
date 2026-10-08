"""Offline place lookup over the GeoNames gazetteer (document 13, section 6.2; ADR-029).

``geonamescache`` bundles cities above 15,000 inhabitants with coordinates and time zones; nothing
is fetched at run time. GeoNames data is CC BY 4.0, so the interface credits GeoNames.

Disambiguation: an exact primary-name match beats alternate names; a country (parameter or named
in the text) narrows the candidates; a name that remains in several countries is *unresolved*
rather than guessed; within one country the most populous city wins. Towns below the gazetteer's
population threshold are unresolved too.
"""

import re
from bisect import bisect_left
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from jobs_radar.domain.geo import normalise_place

_DECORATION = re.compile(r"\([^)]*\)")


@dataclass(frozen=True)
class Place:
    """A resolved city."""

    city: str
    country: str
    label: str
    latitude: float
    longitude: float
    timezone: str
    population: int


class Gazetteer:
    """Resolves place text to cities and searches cities by name prefix."""

    def __init__(self, cities: Iterable[Mapping[str, Any]], countries: Mapping[str, str]) -> None:
        self._cities = list(cities)
        self._country_names = dict(countries)
        self._country_by_name = {normalise_place(n): code for code, n in countries.items()}
        # normalised name -> [(city index, is primary name)]
        self._by_name: dict[str, list[tuple[int, bool]]] = {}
        for index, city in enumerate(self._cities):
            self._by_name.setdefault(normalise_place(city["name"]), []).append((index, True))
            for alternate in city.get("alternatenames", []):
                key = normalise_place(alternate)
                if key:
                    self._by_name.setdefault(key, []).append((index, False))
        self._sorted_names = sorted(self._by_name)

    def _place(self, index: int) -> Place:
        city = self._cities[index]
        code = city["countrycode"]
        country_name = self._country_names.get(code, code)
        return Place(
            city=city["name"],
            country=code,
            label=f"{city['name']}, {country_name}",
            latitude=float(city["latitude"]),
            longitude=float(city["longitude"]),
            timezone=city["timezone"],
            population=int(city["population"]),
        )

    def _country_in(self, parts: list[str]) -> str | None:
        """Return the country named by a trailing part (``Lisbon, Portugal`` or ``Lisbon, PT``)."""
        for part in parts:
            token = part.strip()
            if len(token) == 2 and token.upper() in self._country_names:
                return token.upper()
            if (code := self._country_by_name.get(normalise_place(token))) is not None:
                return code
        return None

    def _candidates(self, name: str, country: str | None) -> list[int]:
        entries = self._by_name.get(name, [])
        primary = [index for index, is_primary in entries if is_primary]
        # An exact primary-name match beats alternate names (``Berlin`` is not North Canton).
        indices = primary or [index for index, _ in entries]
        if country is not None:
            indices = [i for i in indices if self._cities[i]["countrycode"] == country]
        return list(dict.fromkeys(indices))

    def resolve(self, text: str, *, country: str | None = None) -> Place | None:
        """Resolve ``text`` (``Lisbon``, ``Lisbon, Portugal``, ``Lisbon (Hybrid)``) to a city.

        Returns ``None`` when the text is not a known city or is ambiguous across countries.
        """
        parts = _DECORATION.sub("", text).split(",")
        name = normalise_place(parts[0])
        if not name:
            return None
        explicit = country.upper() if country else None
        hint = explicit or self._country_in(parts[1:])
        indices = self._candidates(name, hint)
        if not indices and explicit is None and hint is not None:
            # A trailing token such as the state in ``San Francisco, CA`` may look like a country
            # code; when it matches nothing, fall back to the name alone.
            indices = self._candidates(name, None)
        if not indices or len({self._cities[i]["countrycode"] for i in indices}) > 1:
            return None
        return self._place(max(indices, key=lambda i: self._cities[i]["population"]))

    def search(self, query: str, *, country: str | None = None, limit: int = 10) -> list[Place]:
        """Cities whose name or alternate name starts with ``query``, most populous first."""
        prefix = normalise_place(query)
        if not prefix:
            return []
        found: dict[int, bool] = {}  # city index -> matched by primary name
        start = bisect_left(self._sorted_names, prefix)
        for key in self._sorted_names[start:]:
            if not key.startswith(prefix):
                break
            for index, is_primary in self._by_name[key]:
                found[index] = found.get(index, False) or is_primary
        indices = [
            i for i in found if country is None or self._cities[i]["countrycode"] == country.upper()
        ]
        indices.sort(key=lambda i: (not found[i], -int(self._cities[i]["population"])))
        return [self._place(i) for i in indices[:limit]]


@lru_cache(maxsize=1)
def load_gazetteer() -> Gazetteer:
    """Build the gazetteer from the bundled GeoNames data (done once; no network access)."""
    # Imported lazily: loading the dataset is slow and only needed when places are looked up.
    import geonamescache  # type: ignore[import-untyped]  # the package ships no type information

    data = geonamescache.GeonamesCache()
    countries = {code: info["name"] for code, info in data.get_countries().items()}
    return Gazetteer(data.get_cities().values(), countries)
