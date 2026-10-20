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
        {"areas": [{"key": "electrical", "keywords": ["wiring"]}]},  # arrives in a later phase
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
