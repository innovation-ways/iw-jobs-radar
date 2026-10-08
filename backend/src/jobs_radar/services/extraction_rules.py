"""Checks applied to a model's answer before it is stored (document 13, section 6.2).

* **Evidence:** every quote must occur in the job text; otherwise the attribute becomes ``unknown``
  (and list items are dropped), and what was downgraded is recorded as ``unverified``.
* **Taxonomy:** keys that are not in the live taxonomy are removed and recorded; an attribute left
  without a valid key becomes ``unknown``.
* **Hints:** the source's own fields are given to the model first; when the answer shares nothing
  with them it is flagged as a contradiction (flagged, never overridden).

All functions return new objects; the model's raw answer is never mutated.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from jobs_radar.domain.text_match import normalise_for_match, quote_occurs
from jobs_radar.schemas.extraction import Evidenced, ExtractionOutput

# Attributes that are a single Evidenced value (scalars, lists or objects).
_EVIDENCED_FIELDS = (
    "title",
    "employment_types",
    "hours",
    "work_mode",
    "remote_regions",
    "locations",
    "compensation",
    "seniority_levels",
    "years_required_min",
    "sectors",
    "languages_required",
    "employer_type",
    "education_required",
    "benefits_mentioned",
    "visa_sponsorship",
)

# Evidenced list attributes of taxonomy keys, and the taxonomy kind each is checked against.
_KEY_LISTS = {
    "employment_types": "engagement_type",
    "seniority_levels": "seniority_level",
    "benefits_mentioned": "benefit",
}


@dataclass(frozen=True)
class VerificationResult:
    """The output after evidence checks and the attributes that were downgraded or dropped."""

    output: ExtractionOutput
    unverified: list[str]


@dataclass(frozen=True)
class KeyFilterResult:
    """The output after taxonomy filtering and the keys that were removed (``field:key``)."""

    output: ExtractionOutput
    dropped: list[str]


def verify_evidence(output: ExtractionOutput, title: str, description: str) -> VerificationResult:
    """Downgrade attributes whose quote is not in the job text; drop unverified list items.

    The title counts as job text, because a model may quote it (for example for seniority).
    """
    haystack = f"{title}\n{description}"
    updates: dict[str, Any] = {}
    unverified: list[str] = []
    for field in _EVIDENCED_FIELDS:
        attribute: Evidenced[Any] = getattr(output, field)
        if attribute.status == "known" and not quote_occurs(attribute.evidence or "", haystack):
            updates[field] = Evidenced[Any].unknown()
            unverified.append(field)

    role_families = [r for r in output.role_families if quote_occurs(r.evidence, haystack)]
    unverified += [
        f"role_families:{r.key}"
        for r in output.role_families
        if not quote_occurs(r.evidence, haystack)
    ]
    skills = [s for s in output.skills if quote_occurs(s.evidence, haystack)]
    unverified += [
        f"skills:{s.name}" for s in output.skills if not quote_occurs(s.evidence, haystack)
    ]
    updates["role_families"] = role_families
    updates["skills"] = skills
    return VerificationResult(output.model_copy(update=updates), sorted(unverified))


def keep_known_keys(output: ExtractionOutput, taxonomy: Mapping[str, set[str]]) -> KeyFilterResult:
    """Remove keys that are not in the live taxonomy; an emptied attribute becomes unknown."""
    updates: dict[str, Any] = {}
    dropped: list[str] = []

    for field, kind in _KEY_LISTS.items():
        attribute: Evidenced[list[str]] = getattr(output, field)
        if attribute.status != "known" or attribute.value is None:
            continue
        valid = [key for key in attribute.value if key in taxonomy.get(kind, set())]
        dropped += [f"{field}:{key}" for key in attribute.value if key not in valid]
        if len(valid) != len(attribute.value):
            updates[field] = (
                attribute.model_copy(update={"value": valid}) if valid else Evidenced[Any].unknown()
            )

    employer = output.employer_type
    if employer.status == "known" and employer.value not in taxonomy.get("employer_type", set()):
        dropped.append(f"employer_type:{employer.value}")
        updates["employer_type"] = Evidenced[Any].unknown()

    sectors = output.sectors
    if sectors.status == "known" and sectors.value is not None:
        known_sectors = taxonomy.get("sector", set())
        if sectors.value.primary not in known_sectors:
            dropped.append(f"sectors:{sectors.value.primary}")
            updates["sectors"] = Evidenced[Any].unknown()
        else:
            secondary = [key for key in sectors.value.secondary if key in known_sectors]
            dropped += [f"sectors:{key}" for key in sectors.value.secondary if key not in secondary]
            if len(secondary) != len(sectors.value.secondary):
                value = sectors.value.model_copy(update={"secondary": secondary})
                updates["sectors"] = sectors.model_copy(update={"value": value})

    families = [r for r in output.role_families if r.key in taxonomy.get("role_family", set())]
    dropped += [f"role_families:{r.key}" for r in output.role_families if r not in families]
    updates["role_families"] = families
    return KeyFilterResult(output.model_copy(update=updates), sorted(dropped))


def find_contradictions(
    output: ExtractionOutput, hints: Mapping[str, Sequence[str]]
) -> list[dict[str, Any]]:
    """Flag extracted locations that share nothing with the source's own locations."""
    contradictions: list[dict[str, Any]] = []
    hinted = [location for location in hints.get("locations", []) if location.strip()]
    extracted = output.locations
    if hinted and extracted.status == "known" and extracted.value:
        hint_text = [normalise_for_match(location) for location in hinted]
        overlaps = any(
            h in e or e in h
            for e in (normalise_for_match(item) for item in extracted.value)
            for h in hint_text
        )
        if not overlaps:
            contradictions.append(
                {"attribute": "locations", "hint": list(hinted), "extracted": list(extracted.value)}
            )
    return contradictions
