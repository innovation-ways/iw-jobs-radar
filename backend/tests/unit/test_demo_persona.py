"""The demo persona is fictional and valid against the real schemas (demo seed)."""

from tests.golden import golden_taxonomy

from jobs_radar.demo.persona import DEMO_PROFILE_TITLE, demo_intent, demo_profile
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.profile_api import ProfileInput


def test_profile_validates_and_is_synthetic() -> None:
    profile = ProfileInput.model_validate(demo_profile())
    assert profile.skills, "a demo profile without skills would score nothing"
    text = profile.model_dump_json().lower()
    for private in ("@", "linkedin", "sunrise", "innovation"):
        assert private not in text
    assert DEMO_PROFILE_TITLE


def test_intent_validates_and_rejects_something() -> None:
    intent = IntentDefinition.model_validate(demo_intent(golden_taxonomy()))
    rejected = [
        stance.key for stance in intent.stances.role_families if stance.stance == "rejected"
    ]
    assert rejected, "the set-aside tab needs rejected role families to show"
    assert sum(intent.weights.model_dump().values()) == 100


def test_builders_return_fresh_dictionaries() -> None:
    demo_profile()["skills"].clear()
    assert demo_profile()["skills"]
