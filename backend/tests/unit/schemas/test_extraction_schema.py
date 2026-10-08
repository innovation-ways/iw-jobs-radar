"""Validation rules for the AI extraction output contract (document 13, section 6)."""

from typing import Any

import pytest
from pydantic import ValidationError

from jobs_radar.schemas.extraction import ExtractionOutput


def sample_output() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "title": {"value": "Senior AI Solutions Engineer", "status": "known", "confidence": 1.0, "evidence": "Senior AI Solutions Engineer"},
        "employment_types": {"value": ["contractor_b2b"], "status": "known", "confidence": 0.9, "evidence": "12-month contract"},
        "hours": {"value": None, "status": "unknown", "confidence": 0.0, "evidence": None},
        "work_mode": {"value": "remote", "status": "known", "confidence": 0.95, "evidence": "Fully remote within EU time zones."},
        "remote_regions": {"value": ["EU"], "status": "known", "confidence": 0.9, "evidence": "within EU time zones"},
        "locations": {"value": ["Remote - EU"], "status": "known", "confidence": 0.9, "evidence": "Remote - EU"},
        "compensation": {"value": None, "status": "unknown", "confidence": 0.0, "evidence": None},
        "seniority_levels": {"value": ["senior"], "status": "known", "confidence": 0.9, "evidence": "Senior-level role"},
        "role_families": [{"key": "ai_solutions_engineering", "confidence": 0.93, "evidence": "Design and evaluate LLM-powered features"}],
        "sectors": {"value": {"primary": "enterprise_it", "secondary": []}, "status": "known", "confidence": 0.7, "evidence": "large enterprises"},
        "skills": [{"name": "Python", "importance": "must", "evidence": "Experience with Python"}],
        "languages_required": {"value": [{"language": "en", "level": "C1"}], "status": "known", "confidence": 0.8, "evidence": "fluent English"},
        "employer_type": {"value": "direct_employer", "status": "known", "confidence": 0.8, "evidence": "Join our team"},
        "education_required": {"value": None, "status": "unknown", "confidence": 0.0, "evidence": None},
        "benefits_mentioned": {"value": ["flexible_hours"], "status": "known", "confidence": 0.8, "evidence": "flexible hours"},
        "visa_sponsorship": {"value": None, "status": "unknown", "confidence": 0.0, "evidence": None},
    }  # fmt: skip


def reject(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ExtractionOutput.model_validate(data)


def test_a_valid_output_is_accepted() -> None:
    output = ExtractionOutput.model_validate(sample_output())
    assert output.work_mode.value == "remote"


def test_unknown_fields_are_rejected() -> None:
    data = sample_output()
    data["opinion"] = "great job"
    reject(data)


def test_a_known_attribute_must_quote_its_evidence() -> None:
    data = sample_output()
    data["work_mode"]["evidence"] = None
    reject(data)


def test_an_unknown_attribute_has_no_value() -> None:
    data = sample_output()
    data["hours"]["value"] = "full_time"
    reject(data)


@pytest.mark.parametrize("confidence", [-0.1, 1.5])
def test_confidence_is_a_probability(confidence: float) -> None:
    data = sample_output()
    data["work_mode"]["confidence"] = confidence
    reject(data)


def test_skills_must_quote_evidence() -> None:
    data = sample_output()
    data["skills"][0]["evidence"] = ""
    reject(data)
