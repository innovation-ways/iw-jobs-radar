"""The format of a domain pack file (ADR-080)."""

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from jobs_radar.schemas.pack import PackFile

VALID: dict[str, Any] = {
    "schema_version": 1,
    "key": "construction_trades",
    "version": 1,
    "name": "Construction and skilled trades",
    "description": "Electricians, plumbers, carpenters and site roles.",
    "role_families": [
        {"key": "electrician", "label": "Electrician"},
        {"key": "plumber_pipefitter", "label": "Plumber / pipefitter"},
    ],
    "sectors": [{"key": "construction", "label": "Construction"}],
}


def reject(**changes: Any) -> None:
    with pytest.raises(ValidationError):
        PackFile.model_validate({**deepcopy(VALID), **changes})


def test_a_valid_pack_is_accepted() -> None:
    pack = PackFile.model_validate(VALID)
    assert pack.key == "construction_trades" and len(pack.role_families) == 2


def test_sectors_may_be_left_out() -> None:
    data = deepcopy(VALID)
    del data["sectors"]
    assert PackFile.model_validate(data).sectors == []


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"key": "Not A Key"},
        {"key": ""},
        {"version": 0},
        {"name": ""},
        {"description": ""},
        {"role_families": []},
        {"role_families": [{"key": "Bad Key", "label": "x"}]},
        {"role_families": [{"key": "ok_key", "label": ""}]},
        {"sectors": [{"key": "9starts_with_digit", "label": "x"}]},
        {"unexpected": True},  # nothing may be ignored silently
        {"credentials": [{"name": "", "aliases": []}]},
        {"credentials": [{"name": "Driving licence B", "aliases": ["!!!"]}]},  # nothing to match
        {"credentials": [{"name": "Gas Safe"}, {"name": "gas  safe"}]},  # the same name twice
        {"credentials": [{"label": "Gas Safe"}]},  # the field is `name`
        {"defaults": {"weights": {"not_a_dimension": 5}}},
        {"defaults": {"weights": {"compensation": 41}}},
        {"defaults": {"weights": {"compensation": -1}}},
        {"defaults": {"work_arrangements": {"underwater": "preferred"}}},
        {"defaults": {"work_arrangements": {"remote": "maybe"}}},
        {"defaults": {"schedules": {"day": "rejected", "night": "rejected"}}},  # all rejected
        {"defaults": {"unknown_field": 1}},
        {"areas": [{"key": "electrical", "label": "Electrical", "keywords": []}]},
        {"areas": [{"key": "Bad Key", "label": "Electrical", "keywords": ["wiring"]}]},
        {"areas": [{"key": "electrical", "label": "", "keywords": ["wiring"]}]},
        {"areas": [{"key": "electrical", "label": "E", "keywords": ["wir(ing"]}]},  # no patterns
        {"noise": ["a|b"]},
    ],
)
def test_what_a_pack_cannot_contain(changes: dict[str, Any]) -> None:
    reject(**changes)


def test_keys_and_labels_are_unique_inside_a_list() -> None:
    reject(role_families=[{"key": "a", "label": "One"}, {"key": "a", "label": "Two"}])
    reject(role_families=[{"key": "a", "label": "Same"}, {"key": "b", "label": "same"}])


def test_the_same_key_may_appear_in_role_families_and_sectors() -> None:
    data = deepcopy(VALID)
    data["sectors"] = [{"key": "electrician", "label": "Electrical contracting"}]
    PackFile.model_validate(data)


def test_a_pack_cannot_list_other() -> None:
    """`other` belongs to no pack: it is always offered."""
    reject(role_families=[{"key": "other", "label": "Other"}])
    reject(sectors=[{"key": "other", "label": "Other"}])


def test_areas_and_noise_are_plain_keywords() -> None:
    data = deepcopy(VALID)
    data["areas"] = [
        {"key": "electrical", "label": "Electrical", "keywords": ["electrician", "gas fitt*"]},
        {"key": "plumbing", "label": "Plumbing", "keywords": ["plumber"]},
    ]
    data["noise"] = ["volunteer*", "unpaid"]
    pack = PackFile.model_validate(data)
    assert [a.key for a in pack.areas] == ["electrical", "plumbing"]
    assert pack.noise == ["volunteer*", "unpaid"]


def test_a_pack_without_areas_has_none() -> None:
    pack = PackFile.model_validate(VALID)
    assert pack.areas == [] and pack.noise == []


def test_area_keys_and_labels_are_unique() -> None:
    area = {"key": "electrical", "label": "Electrical", "keywords": ["wiring"]}
    reject(areas=[area, {**area, "label": "Other label"}])
    reject(areas=[area, {**area, "key": "electric_2"}])


def test_credentials_are_names_with_optional_aliases() -> None:
    data = deepcopy(VALID)
    data["credentials"] = [
        {"name": "Driving licence (category B)", "aliases": ["category b licence", "b licence"]},
        {"name": "Gas Safe registration"},
    ]
    pack = PackFile.model_validate(data)
    assert [c.name for c in pack.credentials] == [
        "Driving licence (category B)",
        "Gas Safe registration",
    ]
    assert pack.credentials[1].aliases == []


def test_a_pack_without_credentials_has_none() -> None:
    assert PackFile.model_validate(VALID).credentials == []


def test_defaults_suggest_stances_weights_and_the_credential_gate() -> None:
    data = deepcopy(VALID)
    data["defaults"] = {
        "work_arrangements": {"onsite": "preferred", "remote": "rejected"},
        "schedules": {"day": "preferred", "night": "acceptable"},
        "travel_levels": {"frequent": "rejected", "none": "acceptable"},
        "weights": {"work_arrangement_location": 20, "qualifications": 12, "schedule_travel": 8},
        "reject_missing_credentials": True,
    }
    defaults = PackFile.model_validate(data).defaults
    assert defaults is not None
    assert defaults.work_arrangements == {"onsite": "preferred", "remote": "rejected"}
    assert defaults.weights["qualifications"] == 12 and defaults.reject_missing_credentials is True


def test_a_pack_may_have_no_defaults() -> None:
    assert PackFile.model_validate(VALID).defaults is None
