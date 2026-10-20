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
