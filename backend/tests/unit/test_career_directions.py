"""Career directions in the profile and the weight of their dimension (ADR-057)."""

import pytest
from pydantic import ValidationError
from tests.data import sample_intent, sample_profile_facts, sample_profile_input

from jobs_radar.domain.directions import direction_hash
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.profile import CareerDirection, ProfileFacts
from jobs_radar.schemas.profile_api import ProfileInput

BILLING = "I work as a billing SME and look for telecom roles that fit my skills."


def direction(
    label: str = "Billing SME", text: str = BILLING, **changes: object
) -> dict[str, object]:
    return {"label": label, "text": text, **changes}


def test_a_direction_is_enabled_by_default_and_trims_its_texts() -> None:
    item = CareerDirection.model_validate(direction("  Billing SME ", f"  {BILLING}  "))
    assert (item.label, item.text, item.enabled) == ("Billing SME", BILLING, True)


@pytest.mark.parametrize(
    "changes",
    [
        {"label": ""},
        {"label": "x" * 61},
        {"text": "  "},
        {"text": "x" * 1001},
        {"unknown_field": 1},
    ],
)
def test_an_invalid_direction_is_refused(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CareerDirection.model_validate(direction(**changes))


def test_a_profile_has_no_directions_unless_the_owner_adds_them() -> None:
    facts = ProfileFacts.model_validate(sample_profile_facts())  # a revision made before ADR-057
    assert facts.directions == []
    assert ProfileInput.model_validate(sample_profile_input()).directions == []


def test_at_most_five_directions_with_distinct_labels() -> None:
    many = [direction(f"Goal {n}") for n in range(6)]
    with pytest.raises(ValidationError):
        ProfileInput.model_validate({**sample_profile_input(), "directions": many})
    clash = [direction("Goal"), direction("  goal ", "Another text.")]
    with pytest.raises(ValidationError, match="label"):
        ProfileInput.model_validate({**sample_profile_input(), "directions": clash})
    five = [direction(f"Goal {n}") for n in range(5)]
    assert (
        len(ProfileInput.model_validate({**sample_profile_input(), "directions": five}).directions)
        == 5
    )


def test_the_hash_ignores_spacing_and_changes_with_the_words() -> None:
    assert direction_hash(BILLING) == direction_hash(f"  {BILLING.replace(' ', '  ')}\n")
    assert direction_hash(BILLING) != direction_hash(BILLING + " Also AI.")
    assert direction_hash(BILLING).startswith("sha256:") and len(direction_hash(BILLING)) == 71


def test_the_weight_of_the_dimension_defaults_to_zero_for_existing_intents() -> None:
    weights = IntentDefinition.model_validate(sample_intent()).weights
    assert weights.career_direction == 0
    assert sum(weights.model_dump().values()) == 100


def test_a_cv_import_keeps_the_directions_of_the_current_revision() -> None:
    from types import SimpleNamespace

    from jobs_radar.services.proposal_review import ReviewService

    facts = {**sample_profile_facts(), "directions": [direction()]}
    view = SimpleNamespace(
        revision=SimpleNamespace(facts_json=facts, privacy_json={}),
        skill_names={s["skill_id"]: f"skill{s['skill_id']}" for s in facts["skills"]},
    )
    base, _ = ReviewService._base_input(view)  # type: ignore[arg-type]
    assert base["directions"] == [direction()]
    assert ProfileInput.model_validate({**base, "privacy": {}}).directions[0].label == "Billing SME"
