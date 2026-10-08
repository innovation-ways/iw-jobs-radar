"""Validation rules for the normalised job contract (document 13, section 5)."""

from typing import Any

import pytest
from pydantic import ValidationError
from tests.data import sample_normalised_job

from jobs_radar.schemas.job import NormalisedJob


def reject(data: dict[str, Any], match: str | None = None) -> None:
    with pytest.raises(ValidationError, match=match):
        NormalisedJob.model_validate(data)


def test_the_documented_example_is_valid() -> None:
    job = NormalisedJob.model_validate(sample_normalised_job())
    assert job.title == "Senior AI Solutions Engineer"
    assert job.compensation.status == "unknown"


def test_unknown_fields_are_rejected() -> None:
    data = sample_normalised_job()
    data["mystery"] = 1
    reject(data, "mystery")


def test_a_known_fact_needs_a_value_and_an_unknown_one_must_not_have_one() -> None:
    data = sample_normalised_job()
    data["work_arrangement"]["mode"] = {"value": None, "status": "known"}
    reject(data, "value")
    data = sample_normalised_job()
    data["work_arrangement"]["mode"] = {"value": "remote", "status": "unknown"}
    reject(data, "value")
    data = sample_normalised_job()
    data["work_arrangement"]["mode"] = {"value": None, "status": "unknown"}
    NormalisedJob.model_validate(data)


def test_known_compensation_is_validated() -> None:
    data = sample_normalised_job()
    data["compensation"] = {
        "status": "known",
        "form": "day_rate",
        "currency": "EUR",
        "min": 500,
        "max": 600,
        "period": "day",
        "disclosed": True,
        "assumptions": [],
    }
    job = NormalisedJob.model_validate(data)
    assert job.compensation.status == "known"


def test_compensation_maximum_cannot_be_below_minimum() -> None:
    data = sample_normalised_job()
    data["compensation"] = {
        "status": "known", "form": "day_rate", "currency": "EUR",
        "min": 600, "max": 500, "period": "day", "disclosed": True, "assumptions": [],
    }  # fmt: skip
    reject(data)


def test_unknown_compensation_carries_no_amounts() -> None:
    data = sample_normalised_job()
    data["compensation"] = {"status": "unknown", "min": 1}
    reject(data)


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_role_family_confidence_range(confidence: float) -> None:
    data = sample_normalised_job()
    data["role_families"][0]["confidence"] = confidence
    reject(data)


def test_skill_importance_is_closed() -> None:
    data = sample_normalised_job()
    data["skills"]["required"][0]["importance"] = "maybe"
    reject(data)


def test_timezone_offset_range_must_be_ordered() -> None:
    data = sample_normalised_job()
    data["work_arrangement"]["remote_eligibility"]["timezone_offset_range_hours"] = [3, 1]
    reject(data)


def test_source_is_required() -> None:
    data = sample_normalised_job()
    del data["source"]
    reject(data, "source")
