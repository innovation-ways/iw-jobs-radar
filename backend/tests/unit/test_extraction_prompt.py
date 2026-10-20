"""The extract-v4 prompt: what the model is told and given (document 13, section 6)."""

import json
from collections.abc import Iterator
from typing import Any

from tests.data import SAMPLE_JOB_DESCRIPTION, SAMPLE_JOB_TITLE

from jobs_radar.domain.enums import EXTRACTION_PROMPT_VERSION
from jobs_radar.schemas.extraction import ExtractedSkill
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


def test_the_version_is_extract_v4() -> None:
    assert EXTRACTION_PROMPT_VERSION == "extract-v4"


def test_the_system_message_tells_the_contractor_kinds_apart() -> None:
    """ADR-073: B2B, freelance and agency contracts are three different engagement types."""
    system = prompt().request.system
    for key in ("contractor_b2b", "freelance", "contractor_agency", "employee_fixed_term"):
        assert key in system
    assert "agency" in system.lower()
    assert "day rate" in system.lower()


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


# --- the schema sent to the model is bounded, so an answer cannot loop until it is cut off -------------


def _walk(node: object) -> Iterator[dict[str, Any]]:
    """Yield every dict in a JSON schema."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _prompt_schema() -> dict[str, Any]:
    prepared = build_prompt(title="T", description="D", hints={}, taxonomy={}, max_chars=1000)
    return dict(prepared.request.json_schema)


def test_every_list_in_the_schema_has_a_maximum_size() -> None:
    arrays = [n for n in _walk(_prompt_schema()) if n.get("type") == "array"]
    assert arrays and all("maxItems" in n for n in arrays)


def test_the_prompt_limits_match_the_schema() -> None:
    props = _prompt_schema()["properties"]
    assert props["skills"]["maxItems"] == 25  # rule 7 of the prompt says "at most 25"
    assert props["role_families"]["maxItems"] == 3  # rule 8: one to three families


def test_every_quote_in_the_schema_is_at_most_200_characters() -> None:
    quotes = [n["evidence"] for n in _walk(_prompt_schema()) if isinstance(n.get("evidence"), dict)]
    assert quotes
    for quote in quotes:
        strings = [q for q in (quote.get("anyOf") or [quote]) if q.get("type") == "string"]
        assert strings and all(s.get("maxLength") == 200 for s in strings)  # rule 2


def test_the_validation_model_itself_is_not_tightened() -> None:
    """Stored extractions must keep validating, so only the schema sent to the model is bounded."""
    big = {"name": "x", "importance": "must", "evidence": "q" * 500}
    ExtractedSkill.model_validate(big)


def test_the_lists_are_required_in_the_schema_sent_to_the_model() -> None:
    # Without this the model may leave out `role_families` (a third of the answers did) and the
    # role gate has nothing to judge; an empty list stays allowed for a posting with no role.
    assert {"role_families", "skills"} <= set(_prompt_schema()["required"])


def test_the_model_is_not_asked_for_credentials_before_the_prompt_that_explains_them() -> None:
    """Phase 6a adds the field to the contract; the prompt and its schema change once, in 6b."""
    properties = prompt().request.json_schema["properties"]
    assert "credentials" not in properties
