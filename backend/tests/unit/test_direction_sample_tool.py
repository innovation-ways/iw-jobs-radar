"""Argument parsing of the direction sample tool (ADR-057)."""

import pytest

from jobs_radar.tools.direction_sample import parse_ids, parse_weights


def test_ids_are_a_comma_separated_list_of_positive_numbers() -> None:
    assert parse_ids("4, 17,9") == [4, 17, 9]


@pytest.mark.parametrize("text", ["", "a", "1,,2", "0", "-3"])
def test_bad_ids_are_refused(text: str) -> None:
    with pytest.raises(ValueError, match="id"):
        parse_ids(text)


def test_weights_are_dimension_equals_number_pairs() -> None:
    assert parse_weights("career_direction=15, role_responsibilities=10") == {
        "career_direction": 15,
        "role_responsibilities": 10,
    }


@pytest.mark.parametrize(
    "text", ["career_direction", "nothing=5", "career_direction=41", "career_direction=x"]
)
def test_bad_weights_are_refused(text: str) -> None:
    with pytest.raises(ValueError, match="weight"):
        parse_weights(text)
