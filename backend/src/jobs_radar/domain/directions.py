"""Career directions: the limits and the identity of a direction text (ADR-057). Pure functions."""

import hashlib

MAX_DIRECTIONS = 5
MAX_LABEL_CHARS = 60
MAX_TEXT_CHARS = 1000


def direction_hash(text: str) -> str:
    """Return ``sha256:<hex>`` of the text with its whitespace collapsed.

    A judgement is stored under this hash, so editing only the spacing of a direction never
    invalidates it, while any change to the words judges the job against the new text.
    """
    normalised = " ".join(text.split())
    return f"sha256:{hashlib.sha256(normalised.encode()).hexdigest()}"
