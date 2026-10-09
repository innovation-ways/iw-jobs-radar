"""Offline country lookup used to read the places that job boards publish."""

import pytest

from jobs_radar.adapters.sources.countries import country_code, country_of_place, place_coordinates


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("Portugal", "PT"),
        ("portugal", "PT"),
        ("United States", "US"),
        ("United Kingdom", "GB"),
        ("UK", "GB"),
        ("Czechia", "CZ"),
        ("PT", "PT"),
        ("Atlantis", None),
        ("", None),
    ],
)
def test_country_code(name: str, code: str | None) -> None:
    assert country_code(name) == code


@pytest.mark.parametrize(
    ("place", "code"),
    [
        ("Lisbon", "PT"),
        ("Lisboa", "PT"),
        ("Berlin, Germany", "DE"),
        ("Germany (Remote)", "DE"),
        ("Köln", "DE"),
        ("Remote - Portugal", "PT"),
        ("Remote", None),
        ("", None),
        ("Somewhere unknown", None),
    ],
)
def test_country_of_place(place: str, code: str | None) -> None:
    assert country_of_place(place) == code


@pytest.mark.parametrize(
    ("place", "near", "within_km"),
    [
        ("Lisbon", (38.72, -9.14), 15),
        ("Berlin, Germany", (52.52, 13.40), 15),
        ("Porto", (41.15, -8.61), 15),
    ],
)
def test_place_coordinates_find_the_city(
    place: str, near: tuple[float, float], within_km: float
) -> None:
    from jobs_radar.domain.geo import haversine_km

    found = place_coordinates(place)
    assert found is not None
    assert haversine_km(found[0], found[1], near[0], near[1]) < within_km


@pytest.mark.parametrize("place", ["", "Remote", "Portugal", "Somewhere unknown"])
def test_place_coordinates_need_a_city(place: str) -> None:
    assert place_coordinates(place) is None
