"""Skill-name normalisation shared by validation and storage (document 13, section 2.2)."""

import re

_NON_WORD = re.compile(r"[^a-z0-9+#]+")


def normalise_skill_name(name: str) -> str:
    """Lowercase a skill name and reduce punctuation to single spaces (``Node.js`` -> ``node js``).

    ``+`` and ``#`` are kept so that ``C``, ``C++`` and ``C#`` stay different skills.
    """
    return _NON_WORD.sub(" ", name.lower()).strip()
