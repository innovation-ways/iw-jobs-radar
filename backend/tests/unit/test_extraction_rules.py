"""Evidence verification, taxonomy filtering and hint contradictions for AI extractions."""

from typing import Any

from tests.data import SAMPLE_JOB_DESCRIPTION, SAMPLE_JOB_TITLE, sample_extraction_output

from jobs_radar.schemas.extraction import ExtractionOutput
from jobs_radar.services.extraction_rules import (
    find_contradictions,
    keep_known_keys,
    verify_evidence,
)

TAXONOMY = {
    "role_family": {"ai_solutions_engineering", "data_analysis"},
    "sector": {"enterprise_it", "telecom"},
    "seniority_level": {"senior", "junior"},
    "engagement_type": {"contractor_b2b", "employee_permanent"},
    "employer_type": {"direct_employer", "agency"},
    "benefit": {"flexible_hours"},
}


def output(**changes: Any) -> ExtractionOutput:
    return ExtractionOutput.model_validate({**sample_extraction_output(), **changes})


def known(value: Any, quote: str) -> dict[str, Any]:
    return {"value": value, "status": "known", "confidence": 0.9, "evidence": quote}


# --- evidence ----------------------------------------------------------------------------------


def test_verified_evidence_leaves_the_output_unchanged() -> None:
    original = output()
    result = verify_evidence(original, SAMPLE_JOB_TITLE, SAMPLE_JOB_DESCRIPTION)
    assert result.unverified == []
    assert result.output == original


def test_a_title_quote_is_checked_against_the_title_as_well_as_the_description() -> None:
    result = verify_evidence(
        output(), SAMPLE_JOB_TITLE, "A description that never repeats the title."
    )
    assert "seniority_levels" not in result.unverified  # quoted from the title


def test_an_attribute_whose_quote_is_not_in_the_text_becomes_unknown() -> None:
    changed = output(work_mode=known("hybrid", "three days per week in the office"))
    result = verify_evidence(changed, SAMPLE_JOB_TITLE, SAMPLE_JOB_DESCRIPTION)
    assert result.unverified == ["work_mode"]
    assert result.output.work_mode.status == "unknown"
    assert result.output.work_mode.value is None and result.output.work_mode.evidence is None
    assert result.output.remote_regions.status == "known"  # the others are untouched


def test_paraphrased_quotes_are_not_evidence() -> None:
    changed = output(employment_types=known(["contractor_b2b"], "one year contractor engagement"))
    assert verify_evidence(changed, SAMPLE_JOB_TITLE, SAMPLE_JOB_DESCRIPTION).unverified == [
        "employment_types"
    ]


def test_unknown_attributes_have_nothing_to_verify() -> None:
    assert (
        verify_evidence(output(), SAMPLE_JOB_TITLE, SAMPLE_JOB_DESCRIPTION).output.hours.status
        == "unknown"
    )


def test_list_items_with_unverified_quotes_are_dropped_and_named() -> None:
    changed = output(
        skills=[
            {"name": "Python", "importance": "must", "evidence": "Experience with Python"},
            {"name": "Rust", "importance": "must", "evidence": "deep Rust expertise"},
        ],
        role_families=[
            {"key": "data_analysis", "confidence": 0.8, "evidence": "analyse customer data daily"},
            {
                "key": "ai_solutions_engineering",
                "confidence": 0.9,
                "evidence": "Design and evaluate LLM-powered features",
            },
        ],
    )
    result = verify_evidence(changed, SAMPLE_JOB_TITLE, SAMPLE_JOB_DESCRIPTION)
    assert [s.name for s in result.output.skills] == ["Python"]
    assert [r.key for r in result.output.role_families] == ["ai_solutions_engineering"]
    assert result.unverified == ["role_families:data_analysis", "skills:Rust"]


def test_verification_does_not_modify_its_input() -> None:
    original = output(work_mode=known("hybrid", "three days per week"))
    verify_evidence(original, SAMPLE_JOB_TITLE, SAMPLE_JOB_DESCRIPTION)
    assert original.work_mode.status == "known"


# --- taxonomy keys -------------------------------------------------------------------------------


def test_known_keys_pass_through() -> None:
    result = keep_known_keys(output(), TAXONOMY)
    assert result.dropped == [] and result.output == output()


def test_unknown_keys_are_removed_and_recorded() -> None:
    changed = output(
        employment_types=known(["contractor_b2b", "gig_work"], "12-month contract"),
        role_families=[
            {
                "key": "wizardry",
                "confidence": 0.9,
                "evidence": "Design and evaluate LLM-powered features",
            },
            {
                "key": "ai_solutions_engineering",
                "confidence": 0.9,
                "evidence": "Design and evaluate LLM-powered features",
            },
        ],
    )
    result = keep_known_keys(changed, TAXONOMY)
    assert result.output.employment_types.value == ["contractor_b2b"]
    assert [r.key for r in result.output.role_families] == ["ai_solutions_engineering"]
    assert result.dropped == ["employment_types:gig_work", "role_families:wizardry"]


def test_an_attribute_left_without_valid_keys_becomes_unknown() -> None:
    changed = output(
        seniority_levels=known(["guru"], SAMPLE_JOB_TITLE),
        employer_type=known("mystery", "Join our team"),
        sectors=known(
            {"primary": "space_mining", "secondary": ["telecom", "oil"]}, "large enterprises"
        ),
    )
    result = keep_known_keys(changed, TAXONOMY)
    assert result.output.seniority_levels.status == "unknown"
    assert result.output.employer_type.status == "unknown"
    assert result.output.sectors.status == "unknown"  # the primary sector is invalid
    assert set(result.dropped) == {
        "seniority_levels:guru",
        "employer_type:mystery",
        "sectors:space_mining",
    }


def test_invalid_secondary_sectors_are_dropped_but_a_valid_primary_stays() -> None:
    changed = output(
        sectors=known({"primary": "telecom", "secondary": ["telecom", "oil"]}, "large enterprises")
    )
    result = keep_known_keys(changed, TAXONOMY)
    assert result.output.sectors.value is not None
    assert result.output.sectors.value.secondary == ["telecom"]
    assert result.dropped == ["sectors:oil"]


# --- hints ---------------------------------------------------------------------------------------


def test_matching_locations_do_not_contradict_the_source() -> None:
    assert find_contradictions(output(), {"locations": ["Remote - EU"]}) == []
    lisbon = {
        "value": ["Lisbon"],
        "status": "known",
        "confidence": 0.9,
        "evidence": "work remotely",
    }
    assert find_contradictions(output(locations=lisbon), {"locations": ["Lisbon, Portugal"]}) == []


def test_locations_that_share_nothing_with_the_source_are_flagged() -> None:
    contradictions = find_contradictions(output(), {"locations": ["Berlin, Germany"]})
    assert contradictions == [
        {"attribute": "locations", "hint": ["Berlin, Germany"], "extracted": ["Remote - EU"]}
    ]


def test_no_hint_or_unknown_locations_cannot_contradict() -> None:
    assert find_contradictions(output(), {}) == []
    unknown = {"value": None, "status": "unknown", "confidence": 0.0, "evidence": None}
    assert find_contradictions(output(locations=unknown), {"locations": ["Berlin"]}) == []
