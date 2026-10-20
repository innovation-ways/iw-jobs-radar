"""Characterisation of the extraction prompt, the demo persona and the intents (ADR-080: C2, C6, C11).

These tests freeze what the system does today so that moving the vocabulary out of code (phases 2 to 5)
cannot change the model's instructions, the demo data or the validation of an existing intent.
"""

from collections import defaultdict

from tests.data import SAMPLE_JOB_DESCRIPTION, SAMPLE_JOB_TITLE, sample_intent
from tests.golden import check_golden, golden_optional_terms, golden_taxonomy, load_golden

from jobs_radar.demo.persona import demo_intent, demo_profile
from jobs_radar.schemas.intent import IntentDefinition, validate_intent_against_taxonomy
from jobs_radar.services.extraction_prompt import build_prompt


def current_taxonomy() -> dict[str, set[str]]:
    """The taxonomy of an installation today, read from the golden record (not from the seeds)."""
    grouped: dict[str, set[str]] = defaultdict(set)
    for _id, kind, key, *_rest in load_golden("taxonomy_after_migrations")["terms"]:
        grouped[kind].add(key)
    return dict(grouped)


def test_c2_extraction_prompt_is_byte_for_byte_what_it_is_today() -> None:
    """The worker passes every taxonomy kind, sorted; the whole request is frozen."""
    prepared = build_prompt(
        title=SAMPLE_JOB_TITLE,
        description=SAMPLE_JOB_DESCRIPTION,
        hints={"locations": ["Remote - EU"], "departments": ["Engineering"]},
        taxonomy={kind: sorted(keys) for kind, keys in current_taxonomy().items()},
        max_chars=12000,
    )
    check_golden(
        "extraction_prompt",
        {
            "system": prepared.request.system,
            "user": prepared.request.user,
            "json_schema": prepared.request.json_schema,
            "truncated": prepared.truncated,
        },
    )


def test_c6_today_s_intents_still_validate_against_the_taxonomy() -> None:
    """The documented sample and the demo persona's intent are accepted and complete."""
    for data in (sample_intent(), demo_intent(golden_taxonomy())):
        intent = IntentDefinition.model_validate(data)
        assert (
            validate_intent_against_taxonomy(intent, current_taxonomy(), golden_optional_terms())
            == []
        )
        # A round trip must not lose or add anything.
        assert intent.model_dump(mode="json") == IntentDefinition.model_validate(
            intent.model_dump(mode="json")
        ).model_dump(mode="json")


def test_c11_demo_persona_is_unchanged() -> None:
    """``make demo`` shows the same profile and the same intent stances."""
    check_golden(
        "demo_persona", {"profile": demo_profile(), "intent": demo_intent(golden_taxonomy())}
    )
