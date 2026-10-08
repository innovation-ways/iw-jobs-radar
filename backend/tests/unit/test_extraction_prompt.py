"""The extract-v1 prompt: what the model is told and given (document 13, section 6)."""

import json

from tests.data import SAMPLE_JOB_DESCRIPTION, SAMPLE_JOB_TITLE

from jobs_radar.domain.enums import EXTRACTION_PROMPT_VERSION
from jobs_radar.services.extraction_prompt import build_prompt

TAXONOMY = {
    "role_family": ["ai_solutions_engineering", "data_analysis"],
    "sector": ["telecom"],
    "seniority_level": ["senior"],
    "engagement_type": ["contractor_b2b"],
    "employer_type": ["direct_employer"],
    "benefit": ["flexible_hours"],
}


def prompt(**changes: object):  # type: ignore[no-untyped-def]
    options = {
        "title": SAMPLE_JOB_TITLE,
        "description": SAMPLE_JOB_DESCRIPTION,
        "hints": {"locations": ["Remote - EU"], "departments": ["Engineering"]},
        "taxonomy": TAXONOMY,
        "max_chars": 12000,
        **changes,
    }
    return build_prompt(**options)  # type: ignore[arg-type]


def test_the_version_is_extract_v1() -> None:
    assert EXTRACTION_PROMPT_VERSION == "extract-v1"


def test_the_user_message_has_the_title_description_hints_and_allowed_keys() -> None:
    built = prompt()
    text = built.request.user
    assert SAMPLE_JOB_TITLE in text
    assert SAMPLE_JOB_DESCRIPTION in text
    assert '"locations": ["Remote - EU"]' in text
    for kind, keys in TAXONOMY.items():
        assert kind in text
        for key in keys:
            assert key in text
    assert built.truncated is False


def test_the_system_message_demands_verbatim_evidence_and_forbids_guessing() -> None:
    system = prompt().request.system
    assert "never guess" in system.lower()
    assert "verbatim" in system.lower() or "exact quote" in system.lower()
    assert "unknown" in system
    assert "JSON" in system


def test_the_schema_is_the_extraction_output_contract() -> None:
    schema = prompt().request.json_schema
    assert schema["type"] == "object"
    for field in (
        "title",
        "work_mode",
        "compensation",
        "skills",
        "role_families",
        "visa_sponsorship",
    ):
        assert field in schema["properties"]
    json.dumps(schema)  # serialisable for the provider


def test_a_long_description_is_truncated_and_flagged() -> None:
    built = prompt(description="word " * 5000, max_chars=1000)
    assert built.truncated is True
    assert len(built.description_used) <= 1000
    assert built.description_used in built.request.user
    assert "word " * 5000 not in built.request.user


def test_the_prompt_never_receives_any_profile_or_intent_data() -> None:
    import inspect

    parameters = set(inspect.signature(build_prompt).parameters)
    assert parameters == {"title", "description", "hints", "taxonomy", "max_chars"}


def test_hints_are_labelled_as_possibly_wrong() -> None:
    assert "may be wrong" in prompt().request.user.lower()


def test_empty_hints_are_omitted_cleanly() -> None:
    built = prompt(hints={})
    assert "Source hints" not in built.request.user
