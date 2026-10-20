"""Checks applied to a model's answer before it is stored (document 13, section 6.2).

* **Evidence:** every quote must occur in the job text; otherwise the attribute becomes ``unknown``
  (and list items are dropped), and what was downgraded is recorded as ``unverified``.
* **Taxonomy:** keys that are not in the live taxonomy are removed and recorded; an attribute left
  without a valid key becomes ``unknown``.
* **Hints:** the source's own fields are given to the model first; when the answer shares nothing
  with them it is flagged as a contradiction (flagged, never overridden).

All functions return new objects; the model's raw answer is never mutated.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from jobs_radar.domain.text_match import normalise_for_match, quote_occurs
from jobs_radar.schemas.extraction import (
    Evidenced,
    ExtractedRoleFamily,
    ExtractedSkill,
    ExtractionOutput,
)

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
    "schedule",
    "travel",
)

# Evidenced list attributes of taxonomy keys, and the taxonomy kind each is checked against.
_KEY_LISTS = {
    "employment_types": "engagement_type",
    "seniority_levels": "seniority_level",
    "benefits_mentioned": "benefit",
    "schedule": "schedule",
}


_UNKNOWN: dict[str, Any] = {"value": None, "status": "unknown", "confidence": 0.0, "evidence": None}
_LIST_ITEMS: dict[str, type[ExtractedRoleFamily] | type[ExtractedSkill]] = {
    "role_families": ExtractedRoleFamily,
    "skills": ExtractedSkill,
    "credentials": ExtractedSkill,
}
_EXPECTED = {*_EVIDENCED_FIELDS, *_LIST_ITEMS, "schema_version"}


@dataclass(frozen=True)
class ParsedAnswer:
    """A model answer turned into a valid output, plus what had to be set aside (``notes``)."""

    output: ExtractionOutput
    notes: list[str]


def _clean_attribute(attribute: Any) -> tuple[dict[str, Any], bool]:
    """Return the attribute in contract shape and whether a *known* claim had to be dropped."""
    if not isinstance(attribute, dict) or attribute.get("status") not in ("known", "unknown"):
        return dict(_UNKNOWN), attribute is not None
    if attribute["status"] == "unknown":
        return dict(_UNKNOWN), False  # a stray value on an unknown attribute is simply discarded
    if attribute.get("value") in (None, "", []) or not attribute.get("evidence"):
        return dict(_UNKNOWN), True  # a claim without a value or a quote cannot be checked
    return attribute, False


def parse_lenient(text: str) -> ParsedAnswer:
    """Turn a model answer into a valid :class:`ExtractionOutput`, salvaging what is usable.

    Small models often bend the contract (a value on an ``unknown`` attribute, a missing quote, an
    option outside the list). Instead of rejecting the whole answer, such attributes become
    ``unknown`` (noted, when a claim was lost) and bad list items are dropped (noted as
    ``field:position``). Nothing is invented. An answer that is not an extraction at all is
    rejected.

    Raises:
        ValueError: the text is not JSON, not an object, or has no extraction fields.
    """
    try:
        data = json.loads(text)
    except ValueError as exc:
        msg = "The answer is not an extraction: it is not JSON."
        raise ValueError(msg) from exc
    if not isinstance(data, dict) or not set(data) & _EXPECTED - {"schema_version"}:
        msg = "The answer is not an extraction: no extraction fields found."
        raise ValueError(msg)

    notes: list[str] = []
    fixed: dict[str, Any] = {"schema_version": 1}
    for field in _EVIDENCED_FIELDS:
        fixed[field], lost = _clean_attribute(data.get(field))
        if lost:
            notes.append(field)
    for field, model in _LIST_ITEMS.items():
        items = data.get(field)
        kept: list[dict[str, Any]] = []
        for position, item in enumerate(items if isinstance(items, list) else [], start=1):
            try:
                model.model_validate(item)
            except ValidationError:
                notes.append(f"{field}:{position}")
            else:
                kept.append(item)
        fixed[field] = kept

    # Fields whose value is outside its type fail validation one by one; set those aside.
    for _ in range(2):
        try:
            return ParsedAnswer(ExtractionOutput.model_validate(fixed), sorted(notes))
        except ValidationError as exc:
            failing = {str(error["loc"][0]) for error in exc.errors() if error["loc"]}
            targets = failing & set(_EVIDENCED_FIELDS)
            if not targets:
                break
            for field in targets:
                fixed[field] = dict(_UNKNOWN)
                notes.append(field)
    msg = "The answer is not an extraction: it does not follow the contract."
    raise ValueError(msg)


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
    credentials = [c for c in output.credentials if quote_occurs(c.evidence, haystack)]
    unverified += [
        f"credentials:{c.name}"
        for c in output.credentials
        if not quote_occurs(c.evidence, haystack)
    ]
    updates["role_families"] = role_families
    updates["skills"] = skills
    updates["credentials"] = credentials
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

    travel = output.travel
    if travel.status == "known" and travel.value not in taxonomy.get("travel_level", set()):
        dropped.append(f"travel:{travel.value}")
        updates["travel"] = Evidenced[Any].unknown()

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
