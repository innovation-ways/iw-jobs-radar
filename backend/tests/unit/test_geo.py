"""Distances and place-name normalisation (pure functions)."""

import pytest

from jobs_radar.domain.geo import haversine_km, normalise_place

LISBON = (38.72509, -9.1498)
SETUBAL = (38.5244, -8.8882)
PORTO = (41.1485, -8.61097)


def test_the_distance_between_the_same_point_is_zero() -> None:
    assert haversine_km(*LISBON, *LISBON) == pytest.approx(0)


def test_known_distances_in_portugal() -> None:
    assert 25 < haversine_km(*LISBON, *SETUBAL) < 40  # Setúbal is within a 40 km radius of Lisbon
    assert haversine_km(*LISBON, *PORTO) == pytest.approx(274, abs=8)


def test_distance_is_symmetric() -> None:
    assert haversine_km(*LISBON, *PORTO) == pytest.approx(haversine_km(*PORTO, *LISBON))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Setúbal", "setubal"),
        ("  São   Paulo ", "sao paulo"),
        ("Zürich", "zurich"),
        ("LISBON", "lisbon"),
        ("", ""),
    ],
)
def test_names_are_compared_ignoring_case_accents_and_spacing(raw: str, expected: str) -> None:
    assert normalise_place(raw) == expected
