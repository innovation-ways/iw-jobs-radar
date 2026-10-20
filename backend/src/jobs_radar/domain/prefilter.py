"""Pre-filter rules: which areas of work a posting belongs to, and which words rule it out.

Areas and noise come from the domain packs (ADR-080). They are plain keywords, never regular
expressions typed by a person: every keyword is escaped and compiled here, so a pack cannot contain
a pattern that is invalid or catastrophically slow. A keyword matches whole words, ignoring case; a
trailing ``*`` lets it match any ending (``annotat*`` matches ``annotator`` and ``annotation``).
Hyphens, underscores and slashes count as spaces, so ``back-end`` and ``back end`` are the same.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

# Letters, digits and a few symbols that occur in real titles (c++, c#, node.js, r&d, o'brien).
_ALLOWED = re.compile(r"^[a-z0-9][a-z0-9 +#.&']*\*?$")
_SEPARATORS = re.compile(r"[-_/]")


def _pattern(keywords: Iterable[str]) -> re.Pattern[str] | None:
    """Compile keywords into one whole-word, case-insensitive pattern (``None`` for no keywords)."""
    parts: list[str] = []
    for raw in keywords:
        keyword = " ".join(raw.lower().split())
        if not _ALLOWED.match(keyword):
            msg = f"Not a valid keyword: {raw!r} (letters, digits, spaces and + # . & ' only)"
            raise ValueError(msg)
        prefix = keyword.endswith("*")
        words = keyword.rstrip("*").split(" ")
        body = r"\s+".join(re.escape(word) for word in words)
        parts.append(body + (r"\w*" if prefix else ""))
    if not parts:
        return None
    # Lookarounds instead of \b: a keyword may end in a symbol (c++), where \b would not work.
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)", re.IGNORECASE)


@dataclass(frozen=True)
class Area:
    """An area of work with the keywords that put a posting in it."""

    key: str
    label: str
    keywords: tuple[str, ...]
    _pattern: re.Pattern[str] | None = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_pattern", _pattern(self.keywords))

    def matches(self, text: str) -> bool:
        """Whether the (already normalised) text contains one of the keywords."""
        return self._pattern is not None and self._pattern.search(text) is not None


@dataclass(frozen=True)
class PrefilterRules:
    """The areas and the noise words in force for one owner."""

    areas: tuple[Area, ...]
    noise: tuple[str, ...]
    _noise_pattern: re.Pattern[str] | None = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_noise_pattern", _pattern(self.noise))

    @classmethod
    def empty(cls) -> "PrefilterRules":
        """Rules with no area and no noise (nothing belongs to any area)."""
        return cls((), ())

    @classmethod
    def merged(cls, parts: Sequence["PrefilterRules"]) -> "PrefilterRules":
        """Combine the rules of packs: areas with one key join their keywords, noise is united."""
        keywords: dict[str, list[str]] = {}
        labels: dict[str, str] = {}
        noise: list[str] = []
        for part in parts:
            for area in part.areas:
                labels.setdefault(area.key, area.label)
                known = keywords.setdefault(area.key, [])
                known += [k for k in area.keywords if k not in known]
            noise += [n for n in part.noise if n not in noise]
        areas = tuple(Area(key, labels[key], tuple(words)) for key, words in keywords.items())
        return cls(areas, tuple(noise))

    def allows(self, categories: Sequence[str], texts: Iterable[str]) -> bool:
        """Whether a posting passes an owner's chosen areas.

        Only the chosen areas that these rules define count. When none of them is defined (the pack
        that had them is switched off), there is nothing to filter by and every posting passes.
        """
        known = {area.key for area in self.areas} & set(categories)
        return not known or bool(known & self.categorise(texts))

    def categorise(self, texts: Iterable[str]) -> frozenset[str]:
        """Return the keys of the areas that titles, tags and category names suggest."""
        text = _SEPARATORS.sub(" ", " ".join(texts))
        if self._noise_pattern is not None and self._noise_pattern.search(text):
            return frozenset()
        return frozenset(area.key for area in self.areas if area.matches(text))
