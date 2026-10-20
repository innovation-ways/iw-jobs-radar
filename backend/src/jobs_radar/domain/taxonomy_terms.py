"""Rules for the terms the owner adds to the vocabulary (ADR-080, point 5)."""

import re
import unicodedata

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
