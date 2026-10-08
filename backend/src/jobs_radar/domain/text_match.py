"""Text helpers for verifying AI evidence and bounding what is sent to a model (document 13, 6.2).

Pure functions: no I/O, no application imports.
"""

import re
import unicodedata

_SPACES = re.compile(r"\s+")
_ELLIPSIS = re.compile(r"\.{3}|…")
_PUNCTUATION = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "–": "-",
        "—": "-",
        "‑": "-",
        "−": "-",
        " ": " ",
    }
)
# How far back from the limit a cut may move to land on a word boundary.
_BOUNDARY_WINDOW = 200


def normalise_for_match(text: str) -> str:
    """Lowercase, unify typographic quotes and dashes, and collapse whitespace."""
    folded = unicodedata.normalize("NFKC", text).translate(_PUNCTUATION)
    return _SPACES.sub(" ", folded.casefold()).strip()


def quote_occurs(quote: str, text: str) -> bool:
    """Whether ``quote`` occurs in ``text`` after normalisation.

    A quote joined by an ellipsis (``...`` or ``…``) is accepted when every fragment occurs. An
    empty quote is never evidence.
    """
    haystack = normalise_for_match(text)
    fragments = [normalise_for_match(part) for part in _ELLIPSIS.split(quote)]
    fragments = [fragment for fragment in fragments if fragment]
    return bool(fragments) and all(fragment in haystack for fragment in fragments)


def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Cut ``text`` to at most ``max_chars`` at a word boundary; say whether it was cut."""
    if len(text) <= max_chars:
        return text, False
    cut = text[:max_chars]
    boundary = cut.rfind(" ", max(0, max_chars - _BOUNDARY_WINDOW))
    if boundary == -1:
        boundary = cut.rfind("\n", max(0, max_chars - _BOUNDARY_WINDOW))
    # Only back up when the cut would split a word.
    splits_word = text[max_chars].strip() != "" and cut[-1].strip() != ""
    if splits_word and boundary > 0:
        cut = cut[:boundary]
    return cut.rstrip(), True
