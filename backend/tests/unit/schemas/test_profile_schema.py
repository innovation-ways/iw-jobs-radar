"""Validation rules for the Career Profile facts contract (document 13, section 3)."""

from typing import Any

import pytest
from pydantic import ValidationError
from tests.data import sample_profile_facts

from jobs_radar.schemas.profile import ProfileFacts, ProfilePrivacy


def reject(data: dict[str, Any], match: str | None = None) -> None:
    with pytest.raises(ValidationError, match=match):
        ProfileFacts.model_validate(data)


def test_the_documented_example_is_valid_and_round_trips() -> None:
    data = sample_profile_facts()
    assert ProfileFacts.model_validate(data).model_dump(
        mode="json", exclude_none=True
    ) == _drop_none(data)


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _drop_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_none(v) for v in value]
    return value


def test_unknown_fields_are_rejected() -> None:
    data = sample_profile_facts()
    data["salary_history"] = []
    reject(data, "salary_history")


def test_duplicate_skills_are_rejected() -> None:
    data = sample_profile_facts()
    data["skills"].append(
        {"skill_id": 17, "level": "beginner", "years": 1, "provenance": {"origin": "manual"}}
    )
    reject(data, "duplicate")


@pytest.mark.parametrize("level", ["guru", "", "EXPERT"])
def test_skill_levels_are_closed(level: str) -> None:
    data = sample_profile_facts()
    data["skills"][0]["level"] = level
    reject(data)


@pytest.mark.parametrize("language", ["eng", "EN", "e", ""])
def test_language_codes_are_iso_639_1(language: str) -> None:
    data = sample_profile_facts()
    data["languages"][0]["language"] = language
    reject(data)


@pytest.mark.parametrize("level", ["A1", "B2", "C2", "native"])
def test_language_levels_accept_cefr_and_native(level: str) -> None:
    data = sample_profile_facts()
    data["languages"][1]["level"] = level
    ProfileFacts.model_validate(data)


def test_country_must_be_an_uppercase_iso_code() -> None:
    data = sample_profile_facts()
    data["base_location"]["country"] = "pt"
    reject(data)


def test_timezone_must_be_known() -> None:
    data = sample_profile_facts()
    data["base_location"]["timezone"] = "Nowhere/City"
    reject(data, "timezone")


@pytest.mark.parametrize(("latitude", "longitude"), [(91, 0), (-91, 0), (0, 181), (0, -181)])
def test_coordinates_are_in_range(latitude: float, longitude: float) -> None:
    data = sample_profile_facts()
    data["base_location"].update({"latitude": latitude, "longitude": longitude})
    reject(data)


def test_experience_cannot_end_before_it_starts() -> None:
    data = sample_profile_facts()
    data["experience"][0].update({"start": "2024-06", "end": "2019-01"})
    reject(data, "end")


def test_open_ended_experience_is_allowed() -> None:
    data = sample_profile_facts()
    data["experience"][0]["end"] = None
    ProfileFacts.model_validate(data)


@pytest.mark.parametrize("value", [-1, 71])
def test_years_of_experience_range(value: int) -> None:
    data = sample_profile_facts()
    data["years_experience"] = value
    reject(data)


def test_provenance_origin_is_closed() -> None:
    data = sample_profile_facts()
    data["skills"][0]["provenance"]["origin"] = "rumour"
    reject(data)


def test_privacy_defaults_are_conservative() -> None:
    privacy = ProfilePrivacy()
    assert privacy.redact_contact_details is True
    assert privacy.allow_cloud_processing is False
