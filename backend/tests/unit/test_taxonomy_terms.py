"""Keys of terms the owner adds (ADR-080, phase 3): derived from the label, stable, valid."""

import re

import pytest

from jobs_radar.domain.taxonomy_terms import EDITABLE_KINDS, term_key_from_label

KEY = re.compile(r"^[a-z][a-z0-9_]*$")


@pytest.mark.parametrize(
    ("label", "key"),
    [
        ("Electrician", "electrician"),
        ("HVAC & Refrigeration", "hvac_refrigeration"),
        ("  Câmara   Municipal  ", "camara_municipal"),
        ("Pâtissier / Baker", "patissier_baker"),
        ("Machine-learning ops", "machine_learning_ops"),
        ("3D printing", "term_3d_printing"),  # a key must start with a letter
        ("Operador de Máquinas", "operador_de_maquinas"),
    ],
)
def test_the_key_is_lowercase_ascii_snake_case(label: str, key: str) -> None:
    assert term_key_from_label(label) == key
    assert KEY.match(key)


@pytest.mark.parametrize("label", ["", "   ", "&&& ---", "日本語"])
def test_a_label_without_letters_or_digits_has_no_key(label: str) -> None:
    with pytest.raises(ValueError, match="letter"):
        term_key_from_label(label)


def test_the_key_fits_the_column() -> None:
    key = term_key_from_label("word " * 50)
    assert len(key) <= 80 and KEY.match(key) and not key.endswith("_")


def test_only_role_families_and_sectors_are_editable() -> None:
    """The other vocabularies are the scoring model's own options (ADR-080, point 3)."""
    assert EDITABLE_KINDS == ("role_family", "sector")


# --- merging terms (ADR-080, phase 3) -----------------------------------------------------------------

from jobs_radar.domain.taxonomy_terms import resolve_key, resolve_stances  # noqa: E402


def test_a_key_is_followed_to_the_term_that_replaced_it() -> None:
    assert resolve_key({"a": "b"}, "a") == "b"
    assert resolve_key({"a": "b"}, "other") == "other"
    assert resolve_key({}, "a") == "a"


def test_a_stance_on_a_merged_term_becomes_the_stance_of_the_term_that_replaced_it() -> None:
    assert resolve_stances({"a": "preferred"}, {"a": "b"}) == {"b": "preferred"}


def test_when_both_terms_have_a_stance_the_surviving_term_wins() -> None:
    """ADR-080: the owner's own choice for the term that stays is not overridden."""
    stances = {"a": "preferred", "b": "rejected"}
    assert resolve_stances(stances, {"a": "b"}) == {"b": "rejected"}
    assert resolve_stances({"b": "rejected", "a": "preferred"}, {"a": "b"}) == {"b": "rejected"}


def test_two_merged_terms_without_a_surviving_stance_take_the_first_listed() -> None:
    assert resolve_stances({"a": "acceptable", "c": "rejected"}, {"a": "b", "c": "b"}) == {
        "b": "acceptable"
    }


def test_stances_without_a_merge_are_unchanged_and_keep_their_order() -> None:
    stances = {"x": "preferred", "y": "rejected"}
    assert list(resolve_stances(stances, {}).items()) == list(stances.items())
    assert resolve_stances(stances, {"zzz": "x"}) == stances
