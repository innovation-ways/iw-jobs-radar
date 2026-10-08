"""Content hashing and material-change detection for job postings (LLD section 5).

A change is *material* when it can alter how a job should be read or scored: title, description,
location or apply link. Whitespace, tracking parameters, the order of locations and similar noise
are *cosmetic* and never create a new snapshot or a change event, so the owner is not pulled back
to a job they already reviewed. This module is pure: it imports nothing from the application.
"""

import hashlib
import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# The fields that make up a posting's material content, in the order changes are reported.
MATERIAL_FIELDS = ("title", "description", "locations", "apply_url")

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_PARAMS = frozenset(
    {
        "gh_src",
        "gh_jid_src",
        "lever-source",
        "lever-origin",
        "source",
        "ref",
        "referrer",
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
    }
)


def normalise_text(value: str) -> str:
    """Collapse every run of whitespace to one space and trim the ends."""
    return " ".join(value.split())


def canonical_url(url: str) -> str:
    """Return ``url`` without tracking parameters or fragment, host lower-cased, query sorted.

    A string that is not a usable URL is returned unchanged rather than raising.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.scheme or not parts.netloc:
        return url
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith(_TRACKING_PREFIXES) and key.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(sorted(kept))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ""))


def material_fields(
    *, title: str, description_text: str, locations: Iterable[str], apply_url: str
) -> dict[str, Any]:
    """Canonical form of the material fields of a posting, ready to hash or compare."""
    return {
        "title": normalise_text(title),
        "description": normalise_text(description_text),
        "locations": sorted(
            {normalise_text(location) for location in locations if location.strip()}
        ),
        "apply_url": canonical_url(apply_url),
    }


def content_hash(material: dict[str, Any]) -> str:
    """``sha256:<hex>`` of the canonical JSON of ``material``."""
    payload = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def changed_fields(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Names of the material fields that differ, in the fixed order of :data:`MATERIAL_FIELDS`."""
    return [name for name in MATERIAL_FIELDS if old.get(name) != new.get(name)]
