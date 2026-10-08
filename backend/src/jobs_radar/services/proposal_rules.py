"""Turn a model's answer into reviewable proposal items (T6.5, document 06 section 6).

The answer is a list of ``{path, value, excerpt, confidence}``. Each item is validated on its own
against the profile input models; an invalid one is dropped (and counted), so one bad item never
discards the rest. An excerpt must occur in the document text, otherwise it is removed and the
confidence is capped: a quote the owner cannot find in their own CV is not evidence. Nothing here
is stored as a profile fact; the owner decides item by item.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from jobs_radar.domain.text_match import quote_occurs
from jobs_radar.schemas.common import CountryCode
from jobs_radar.schemas.profile import LanguageSkill, ShortText
from jobs_radar.schemas.profile_api import (
    CertificationInput,
    EducationInput,
    ExperienceInput,
    SkillInput,
)

EXCERPT_LIMIT = 300
UNVERIFIED_CONFIDENCE_CAP = 0.5
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class _Headline(BaseModel):
    value: ShortText


class _Years(BaseModel):
    value: int


class _Place(BaseModel):
    """A place as the CV states it; the time zone is resolved when the item is accepted."""

    place: ShortText
    country: CountryCode


# Single-valued paths (one value per profile) and list paths (one item per element).
SINGLE_PATHS = ("headline", "years_experience", "base_location")
LIST_PATHS = ("languages", "skills", "experience", "education", "certifications")
_MODELS: dict[str, type[BaseModel]] = {
    "base_location": _Place,
    "languages": LanguageSkill,
    "skills": SkillInput,
    "experience": ExperienceInput,
    "education": EducationInput,
    "certifications": CertificationInput,
}


@dataclass(frozen=True)
class DraftItem:
    """One validated proposed fact."""

    path: str
    value: Any
    excerpt: str | None
    confidence: float


@dataclass(frozen=True)
class DraftResult:
    """The salvaged items and how many entries had to be dropped."""

    items: list[DraftItem]
    dropped: int


def validate_value(path: str, raw: Any) -> Any:
    """Return the normalised value for ``path`` or raise ``ValueError``/``ValidationError``."""
    if path == "headline":
        return _Headline(value=raw.strip() if isinstance(raw, str) else raw).value
    if path == "years_experience":
        if isinstance(raw, bool):
            raise ValueError("not a number")
        years = _Years(value=raw).value
        if not 0 <= years <= 70:
            raise ValueError("years out of range")
        return years
    model = _MODELS.get(path)
    if model is None:
        raise ValueError("unknown path")
    return model.model_validate(raw).model_dump(mode="json")


def _dedupe_key(item: DraftItem) -> str | None:
    value = item.value
    if item.path == "skills":
        return str(value["name"]).casefold()
    if item.path == "languages":
        return str(value["language"])
    if item.path == "experience":
        return f"{value['title']}|{value['organisation']}|{value['start']}".casefold()
    if item.path == "education":
        return f"{value['level']}|{value['field']}".casefold()
    if item.path == "certifications":
        return str(value["name"]).casefold()
    return None


def parse_draft(answer: str, text: str) -> DraftResult:
    """Validate the model's ``answer`` against ``text``, the document the items must come from."""
    try:
        payload = json.loads(_FENCE.sub("", answer.strip()))
        entries = payload["items"]
    except (ValueError, KeyError, TypeError):
        return DraftResult([], 0)
    if not isinstance(entries, list):
        return DraftResult([], 0)

    kept: list[DraftItem] = []
    dropped = 0
    for entry in entries:
        try:
            path = entry["path"]
            value = validate_value(path, entry["value"])
            confidence = min(1.0, max(0.0, float(entry.get("confidence", 0.5))))
            excerpt = entry.get("excerpt")
        except (KeyError, TypeError, ValueError, ValidationError):
            dropped += 1
            continue
        if isinstance(excerpt, str) and excerpt.strip() and quote_occurs(excerpt, text):
            excerpt = " ".join(excerpt.split())[:EXCERPT_LIMIT]
        else:
            excerpt, confidence = None, min(confidence, UNVERIFIED_CONFIDENCE_CAP)
        kept.append(DraftItem(path, value, excerpt, confidence))

    # One value per single-valued path, and one item per skill, language, role... : keep the best.
    best: dict[tuple[str, str | None], DraftItem] = {}
    for item in kept:
        key = (item.path, _dedupe_key(item))
        if key not in best or item.confidence > best[key].confidence:
            best[key] = item
    order = list(SINGLE_PATHS) + list(LIST_PATHS)
    items = sorted(best.values(), key=lambda i: order.index(i.path))
    return DraftResult(items, dropped)
