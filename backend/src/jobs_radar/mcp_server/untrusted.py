"""Wrapper for text written by third parties (job postings, company pages), ADR-078 point 6.

Such text can contain instructions aimed at an agent (prompt injection). It is returned only
inside a fixed marker, truncated, with any marker found in the text neutralised, so an agent (and
the tool descriptions, which say so) can tell data from instructions.
"""

import re

OPEN = "<untrusted-source-text>"
CLOSE = "</untrusted-source-text>"

# Matches the start of either marker, whatever the case, so the text cannot close or reopen ours.
_MARKER_START = re.compile(r"<(/?)untrusted-source-text", re.IGNORECASE)


def wrap_untrusted(text: str, *, max_chars: int) -> str:
    """Return ``text`` truncated to ``max_chars`` and wrapped in the untrusted-text marker.

    Marker look-alikes inside the text are rewritten first, then the text is cut, so neither the
    cut nor the content can forge a closing marker.
    """
    safe = _MARKER_START.sub(r"[\1untrusted-source-text", text)
    shown = safe[:max_chars]
    note = ""
    if len(safe) > max_chars:
        note = f"\n[truncated: {len(safe) - max_chars} more characters not shown]"
    return f"{OPEN}\n{shown}{note}\n{CLOSE}"
