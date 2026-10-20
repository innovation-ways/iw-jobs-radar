"""Rules for the terms the owner adds to the vocabulary and merges (ADR-080, point 5)."""

import re
import unicodedata
from collections.abc import Mapping

# Only these vocabularies are the owner's to extend. The others (seniority, work arrangement,
# engagement, employer type, benefits) are options of the scoring model itself.
EDITABLE_KINDS = ("role_family", "sector")

_MAX_KEY_LENGTH = 80  # the length of ``taxonomy_term.term_key``
_NOT_KEY_CHARACTERS = re.compile(r"[^a-z0-9]+")


def term_key_from_label(label: str) -> str:
    """Derive the stable key of a new term from its label.

    The key is lowercase ASCII snake case (accents folded), starts with a letter and fits the
    column. It never changes afterwards, even if the label does, because intents, extractions and
    evaluations refer to it.

    Raises:
        ValueError: if the label has no letter or digit that can be kept.
    """
    folded = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii")
    key = _NOT_KEY_CHARACTERS.sub("_", folded.lower()).strip("_")
    if not key:
        msg = "The label needs at least one letter or digit that a key can be made from."
        raise ValueError(msg)
    if not key[0].isalpha():
        key = f"term_{key}"
    return key[:_MAX_KEY_LENGTH].rstrip("_")


def resolve_key(replacements: Mapping[str, str], key: str) -> str:
    """Return the key of the term that replaced ``key`` (followed to the end), or ``key`` itself."""
    return replacements.get(key, key)


def resolve_stances(stances: Mapping[str, str], replacements: Mapping[str, str]) -> dict[str, str]:
    """Express a map of ``term key -> stance`` in the terms that exist after merges (ADR-080).

    A stance on a merged term becomes the stance of the term that replaced it. When the owner had
    also chosen a stance for that surviving term, the surviving term's own stance wins; when several
    merged terms had stances and the survivor had none, the first one listed is used. Without
    merges the stances come back unchanged and in the same order.
    """
    resolved: dict[str, str] = {}
    for key, stance in stances.items():
        if key not in replacements:
            resolved[key] = stance
    for key, stance in stances.items():
        if key in replacements:
            resolved.setdefault(resolve_key(replacements, key), stance)
    return resolved
