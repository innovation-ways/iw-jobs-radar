"""Offline country lookup used to read the places that job boards publish."""

import pytest

from jobs_radar.adapters.sources.countries import country_code, country_of_place


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
