"""Validation rules for the Search Intent contract (document 13, section 4.1)."""

from copy import deepcopy
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError
from tests.data import sample_intent

from jobs_radar.domain.taxonomy_seed import TAXONOMY_SEED_V1
from jobs_radar.schemas.intent import (
    IntentDefinition,
    Weights,
    validate_intent_against_taxonomy,
)


def make(**changes: Any) -> dict[str, Any]:
    """The sample intent with top-level fields replaced."""
    data = sample_intent()
    data.update(changes)
    return data


def reject(data: dict[str, Any], match: str | None = None) -> None:
    with pytest.raises(ValidationError, match=match):
        IntentDefinition.model_validate(data)


def test_the_documented_example_is_valid_and_round_trips() -> None:
    data = sample_intent()
    intent = IntentDefinition.model_validate(data)
    assert intent.model_dump(mode="json") == data


def test_unknown_fields_are_rejected_at_every_level() -> None:
    reject(make(surprise=1), "surprise")
    data = sample_intent()
    data["stances"]["role_families"][0]["colour"] = "red"
    reject(data, "colour")
    data = sample_intent()
    data["weights"]["luck"] = 5
    reject(data, "luck")


# --- weights -----------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [-1, 41, 100])
def test_weight_outside_0_to_40_is_rejected(value: int) -> None:
    data = sample_intent()
    data["weights"]["compensation"] = value
    reject(data)


def test_all_zero_weights_are_rejected() -> None:
    data = sample_intent()
    data["weights"] = dict.fromkeys(data["weights"], 0)
    reject(data, "at least one weight")


def test_one_nonzero_weight_is_enough() -> None:
    data = sample_intent()
    data["weights"] = dict.fromkeys(data["weights"], 0) | {"compensation": 1}
    assert IntentDefinition.model_validate(data).weights.compensation == 1


def test_optional_dimensions_default_to_zero_and_defaults_total_100() -> None:
    weights = Weights()
    assert weights.benefits_flexibility == 0
    assert weights.qualifications == 0
    assert sum(weights.model_dump().values()) == 100


# --- compensation --------------------------------------------------------------------------------


def test_minimum_above_target_is_rejected() -> None:
    data = sample_intent()
    data["compensation"]["contractor_day_rate"] = {"currency": "EUR", "minimum": 600, "target": 500}
    reject(data, "target")


def test_negative_pay_is_rejected() -> None:
    data = sample_intent()
    data["compensation"]["employee_pay"]["annual_minimum"] = -1
    reject(data)


@pytest.mark.parametrize("payments", [11, 13, 15])
def test_only_12_or_14_payments_are_accepted(payments: int) -> None:
    data = sample_intent()
    data["compensation"]["employee_pay"]["payments_per_year"] = payments
    reject(data)


@pytest.mark.parametrize("currency", ["eur", "EURO", "E1R", ""])
def test_currency_must_be_an_iso_4217_code(currency: str) -> None:
    data = sample_intent()
    data["compensation"]["contractor_day_rate"]["currency"] = currency
    reject(data)


def test_contractor_pay_has_no_monthly_or_annual_form() -> None:
    data = sample_intent()
    data["compensation"]["contractor_day_rate"]["annual_minimum"] = 1
    reject(data, "annual_minimum")


def test_either_pay_form_may_be_absent() -> None:
    data = sample_intent()
    data["compensation"]["employee_pay"] = None
    assert IntentDefinition.model_validate(data).compensation.employee_pay is None


def test_monthly_figures_are_derived_from_the_annual_amount() -> None:
    pay = IntentDefinition.model_validate(sample_intent()).compensation.employee_pay
    assert pay is not None
    assert pay.monthly_minimum == pytest.approx(60000 / 14)
    assert pay.monthly_target == pytest.approx(75000 / 14)


@given(
    annual=st.floats(min_value=0, max_value=1_000_000, allow_nan=False),
    payments=st.sampled_from([12, 14]),
)
def test_switching_payments_per_year_keeps_the_annual_amount(annual: float, payments: int) -> None:
    data = sample_intent()
    data["compensation"]["employee_pay"].update(
        {"payments_per_year": payments, "annual_minimum": annual, "annual_target": annual}
    )
    pay = IntentDefinition.model_validate(data).compensation.employee_pay
    assert pay is not None
    assert pay.annual_minimum == annual  # annual is canonical
    assert pay.monthly_minimum * payments == pytest.approx(annual)


# --- stances and coherence ------------------------------------------------------------------------


def test_all_role_families_rejected_is_incoherent() -> None:
    data = sample_intent()
    for entry in data["stances"]["role_families"]:
        entry["stance"] = "rejected"
    reject(data, "at least one option")


def test_empty_role_families_are_incoherent() -> None:
    data = sample_intent()
    data["stances"]["role_families"] = []
    reject(data, "role_families")


def test_empty_sector_list_means_no_sector_preference() -> None:
    data = sample_intent()
    data["stances"]["sectors"] = []
    assert IntentDefinition.model_validate(data).stances.sectors == []


def test_all_work_arrangements_rejected_is_incoherent() -> None:
    data = sample_intent()
    for entry in data["stances"]["work_arrangements"]:
        entry["stance"] = "rejected"
    reject(data, "at least one option")


def test_duplicate_keys_in_a_group_are_rejected() -> None:
    data = sample_intent()
    data["stances"]["sectors"].append({"key": "telecom", "stance": "acceptable"})
    reject(data, "duplicate")


def test_invalid_stance_value_is_rejected() -> None:
    data = sample_intent()
    data["stances"]["sectors"][0]["stance"] = "love"
    reject(data)


# --- rules and other fields ---------------------------------------------------------------------------


@pytest.mark.parametrize("region", ["eu", "XYZ", "E", "", "Europe"])
def test_invalid_regions_are_rejected(region: str) -> None:
    data = sample_intent()
    data["work_rules"]["remote"]["eligible_regions"] = [region]
    reject(data)


@pytest.mark.parametrize("region", ["EU", "EEA", "EUROPE", "UK", "WORLD", "PT", "US"])
def test_valid_regions_are_accepted(region: str) -> None:
    data = sample_intent()
    data["work_rules"]["remote"]["eligible_regions"] = [region]
    IntentDefinition.model_validate(data)


def test_remote_needs_at_least_one_region() -> None:
    data = sample_intent()
    data["work_rules"]["remote"]["eligible_regions"] = []
    reject(data)


def test_timezone_must_be_a_known_iana_name() -> None:
    data = sample_intent()
    data["work_rules"]["remote"]["timezone"] = "Mars/Olympus"
    reject(data, "timezone")


@pytest.mark.parametrize("tolerance", [-1, 13])
def test_timezone_tolerance_is_limited(tolerance: int) -> None:
    data = sample_intent()
    data["work_rules"]["remote"]["timezone_tolerance_hours"] = tolerance
    reject(data)


def test_timezone_tolerance_may_be_unlimited() -> None:
    data = sample_intent()
    data["work_rules"]["remote"]["timezone_tolerance_hours"] = None
    IntentDefinition.model_validate(data)


@pytest.mark.parametrize("radius", [0, 501])
def test_radius_is_limited(radius: int) -> None:
    data = sample_intent()
    data["work_rules"]["onsite_hybrid"]["radius_km"] = radius
    reject(data)


@pytest.mark.parametrize("languages", [[], ["eng"], ["EN"], ["e"]])
def test_languages_must_be_iso_639_1_and_not_empty(languages: list[str]) -> None:
    data = sample_intent()
    data["languages"]["can_work_in"] = languages
    reject(data)


def test_keyword_limits() -> None:
    reject(make(keywords=[f"k{i}" for i in range(51)]))
    reject(make(keywords=["x" * 61]))
    IntentDefinition.model_validate(make(keywords=["x" * 60]))


@pytest.mark.parametrize("threshold", [-1, 101])
def test_alert_threshold_range(threshold: int) -> None:
    reject(make(alert_threshold=threshold))


@pytest.mark.parametrize("title", ["", "x" * 121])
def test_title_length(title: str) -> None:
    reject(make(title=title))


def test_posting_age_filter_range() -> None:
    data = sample_intent()
    data["filters"]["max_posting_age_days"] = 0
    reject(data)
    data["filters"]["max_posting_age_days"] = 30
    IntentDefinition.model_validate(data)


# --- taxonomy completeness (needs the taxonomy, so it is a separate check) ------------------------------


def taxonomy() -> dict[str, set[str]]:
    return {kind: set(keys) for kind, keys in TAXONOMY_SEED_V1.items()}


def test_sample_intent_is_complete_against_the_seed_taxonomy() -> None:
    intent = IntentDefinition.model_validate(sample_intent())
    assert validate_intent_against_taxonomy(intent, taxonomy()) == []


def test_closed_groups_must_list_every_term() -> None:
    data = sample_intent()
    data["stances"]["work_arrangements"] = data["stances"]["work_arrangements"][:2]
    errors = validate_intent_against_taxonomy(IntentDefinition.model_validate(data), taxonomy())
    assert any("work_arrangements" in e and "onsite" in e for e in errors), errors


def test_unknown_keys_are_reported() -> None:
    data = sample_intent()
    data["stances"]["role_families"].append({"key": "wizardry", "stance": "preferred"})
    errors = validate_intent_against_taxonomy(IntentDefinition.model_validate(data), taxonomy())
    assert any("wizardry" in e for e in errors), errors


def test_open_groups_may_list_a_subset() -> None:
    data = deepcopy(sample_intent())
    data["stances"]["sectors"] = [{"key": "telecom", "stance": "preferred"}]
    assert validate_intent_against_taxonomy(IntentDefinition.model_validate(data), taxonomy()) == []


def test_a_term_added_after_version_one_may_be_missing_from_an_older_intent() -> None:
    """ADR-073: an intent saved before ``contractor_agency`` existed stays valid."""
    live = {**taxonomy(), "engagement_type": {*taxonomy()["engagement_type"], "contractor_agency"}}
    intent = IntentDefinition.model_validate(sample_intent())
    optional = {"engagement_type": frozenset({"contractor_agency"})}
    assert validate_intent_against_taxonomy(intent, live, optional) == []


def test_a_term_that_is_not_optional_must_be_listed() -> None:
    """Optional terms come from the database; without them a missing option is an error."""
    live = {**taxonomy(), "engagement_type": {*taxonomy()["engagement_type"], "contractor_agency"}}
    intent = IntentDefinition.model_validate(sample_intent())
    errors = validate_intent_against_taxonomy(intent, live, {})
    assert any("engagement_types" in e and "contractor_agency" in e for e in errors), errors


def test_an_intent_may_still_set_a_stance_for_a_later_term() -> None:
    live = {**taxonomy(), "engagement_type": {*taxonomy()["engagement_type"], "contractor_agency"}}
    data = deepcopy(sample_intent())
    data["stances"]["engagement_types"].append({"key": "contractor_agency", "stance": "preferred"})
    assert validate_intent_against_taxonomy(IntentDefinition.model_validate(data), live) == []


def test_rejecting_missing_credentials_is_an_option_that_is_off_by_default() -> None:
    """ADR-080, phase 6a: like rejecting unspoken languages, but off unless the owner turns it on."""
    data = sample_intent()
    assert IntentDefinition.model_validate(data).filters.reject_missing_credentials is False
    data["filters"]["reject_missing_credentials"] = True
    assert IntentDefinition.model_validate(data).filters.reject_missing_credentials is True


# --- schedule and travel (ADR-080, phase 6b) ---------------------------------------------------------------


def taxonomy_with_new_kinds() -> dict[str, set[str]]:
    return {
        **taxonomy(),
        "schedule": {"day", "night", "rotating_shifts", "weekends", "on_call"},
        "travel_level": {"none", "occasional", "frequent"},
    }


def later_terms() -> dict[str, frozenset[str]]:
    return {
        "schedule": frozenset({"day", "night", "rotating_shifts", "weekends", "on_call"}),
        "travel_level": frozenset({"none", "occasional", "frequent"}),
    }


def test_the_schedule_and_travel_groups_are_optional_and_older_intents_have_none() -> None:
    data = sample_intent()
    del data["stances"]["schedules"], data["stances"]["travel_levels"]
    stances = IntentDefinition.model_validate(data).stances
    assert stances.schedules == [] and stances.travel_levels == []


def test_schedule_and_travel_take_stances_like_every_other_group() -> None:
    data = sample_intent()
    data["stances"]["schedules"] = [
        {"key": "day", "stance": "preferred"},
        {"key": "night", "stance": "rejected"},
    ]
    data["stances"]["travel_levels"] = [{"key": "none", "stance": "acceptable"}]
    intent = IntentDefinition.model_validate(data)
    assert [e.key for e in intent.stances.schedules] == ["day", "night"]
    assert validate_intent_against_taxonomy(intent, taxonomy_with_new_kinds(), later_terms()) == []


def test_a_group_that_rejects_everything_is_incoherent() -> None:
    data = sample_intent()
    data["stances"]["schedules"] = [{"key": "day", "stance": "rejected"}]
    with pytest.raises(ValidationError, match="at least one option"):
        IntentDefinition.model_validate(data)


def test_an_unknown_working_pattern_is_reported() -> None:
    data = sample_intent()
    data["stances"]["schedules"] = [{"key": "graveyard", "stance": "preferred"}]
    errors = validate_intent_against_taxonomy(
        IntentDefinition.model_validate(data), taxonomy_with_new_kinds(), later_terms()
    )
    assert any("schedules" in e and "graveyard" in e for e in errors), errors


def test_the_new_terms_are_optional_so_an_older_intent_stays_valid() -> None:
    intent = IntentDefinition.model_validate(sample_intent())
    assert validate_intent_against_taxonomy(intent, taxonomy_with_new_kinds(), later_terms()) == []
    # Without being told they are optional, the missing options would be an error.
    errors = validate_intent_against_taxonomy(intent, taxonomy_with_new_kinds(), {})
    assert any("schedules: missing options" in e for e in errors)


def test_the_weight_of_schedule_and_travel_is_off_unless_chosen() -> None:
    assert IntentDefinition.model_validate(sample_intent()).weights.schedule_travel == 0
    data = sample_intent()
    data["weights"]["schedule_travel"] = 12
    assert IntentDefinition.model_validate(data).weights.schedule_travel == 12
    data["weights"]["schedule_travel"] = 41
    with pytest.raises(ValidationError):
        IntentDefinition.model_validate(data)
