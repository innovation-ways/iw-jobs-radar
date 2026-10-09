"""``dedup-v1``: deciding whether two listings are the same real opportunity (document 13, 10).

Pure functions. Two listings are candidates only when they belong to the same company, come from
different sources and have a compatible location. The similarity is
``0.35 title + 0.45 description + 0.10 date proximity + 0.10 location``; thresholds and weights are
the initial constants of the policy. Nothing here touches the database or a model.
"""

import math
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from rapidfuzz import fuzz

from jobs_radar.domain.geo import normalise_place
from jobs_radar.domain.regions import regions_intersect

POLICY_VERSION = "dedup-v1"

TITLE_WEIGHT, DESCRIPTION_WEIGHT, DATE_WEIGHT, LOCATION_WEIGHT = 0.35, 0.45, 0.10, 0.10
AUTO_THRESHOLD = 0.90
POSSIBLE_THRESHOLD = 0.75
SAME_SOURCE_POSSIBLE_THRESHOLD = 0.95
SHINGLE_WORDS = 5
# Sources that are the employer's own applicant tracking system (preferred as the primary listing).
EMPLOYER_SOURCES = frozenset({"greenhouse", "lever", "ashby", "smartrecruiters"})

Location = Literal["identical", "overlap", "none"]
Decision = Literal["auto", "possible", "distinct"]
_WORDS = re.compile(r"\w+")
_LOCATION_SCORE: dict[Location, float] = {"identical": 1.0, "overlap": 0.5, "none": 0.0}


def _words(text: str) -> list[str]:
    return _WORDS.findall(normalise_place(text))


def title_similarity(a: str, b: str) -> float:
    """Token-set ratio of two titles from 0 to 1 (case, order and punctuation are ignored)."""
    left, right = " ".join(_words(a)), " ".join(_words(b))
    return float(fuzz.token_set_ratio(left, right)) / 100.0


def shingles(text: str) -> frozenset[tuple[str, ...]]:
    """Return the five-word windows of the normalised text (one window if it is shorter)."""
    words = _words(text)
    if not words:
        return frozenset()
    if len(words) <= SHINGLE_WORDS:
        return frozenset({tuple(words)})
    return frozenset(
        tuple(words[i : i + SHINGLE_WORDS]) for i in range(len(words) - SHINGLE_WORDS + 1)
    )


def jaccard[T](a: Collection[T], b: Collection[T]) -> float:
    """Return the Jaccard similarity of two collections (0 when either is empty)."""
    left, right = set(a), set(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def cosine(u: Sequence[float], v: Sequence[float]) -> float:
    """Return the cosine similarity of two vectors, clamped to 0 to 1 (0 for a zero vector)."""
    norm = math.sqrt(sum(x * x for x in u)) * math.sqrt(sum(y * y for y in v))
    if norm == 0:
        return 0.0
    return max(0.0, min(1.0, sum(x * y for x, y in zip(u, v, strict=True)) / norm))


def date_proximity(a: datetime | None, b: datetime | None) -> float:
    """Return 1 within 14 days, 0.5 within 30, else 0 (0 when a date is missing)."""
    if a is None or b is None:
        return 0.0
    days = abs((a - b).total_seconds()) / 86400
    if days <= 14:
        return 1.0
    return 0.5 if days <= 30 else 0.0


def _location_key(raw: str) -> tuple[str, tuple[str, ...]]:
    """Return ``(key, regions)``; remote places become ``remote`` plus their region words."""
    words = _words(raw)
    if "remote" in words:
        regions = tuple(sorted(w for w in words if w != "remote"))
        return "remote:" + ",".join(regions), regions
    return " ".join(words), ()


def location_relation(a: Sequence[str], b: Sequence[str]) -> Location:
    """Return how two sets of places relate: identical, overlapping, or not at all."""
    keys_a = {_location_key(x) for x in a if x.strip()}
    keys_b = {_location_key(x) for x in b if x.strip()}
    if not keys_a or not keys_b:
        return "none"
    if {k for k, _ in keys_a} == {k for k, _ in keys_b}:
        return "identical"
    if {k for k, _ in keys_a} & {k for k, _ in keys_b}:
        return "overlap"
    for key_a, regions_a in keys_a:
        for key_b, regions_b in keys_b:
            if key_a.startswith("remote:") and key_b.startswith("remote:"):
                if not regions_a or not regions_b:
                    return "overlap"  # a remote job with no stated region is open to the other's
                upper_a, upper_b = [r.upper() for r in regions_a], [r.upper() for r in regions_b]
                forward, backward = (
                    regions_intersect(upper_a, upper_b),
                    regions_intersect(upper_b, upper_a),
                )
                # Regions we cannot read (None) must not make two listings "distinct".
                if forward is None or backward is None or forward or backward:
                    return "overlap"
    return "none"


@dataclass(frozen=True)
class Similarity:
    """The similarity of two listings and the features it was computed from."""

    score: float
    features: dict[str, Any]


def similarity(*, title: float, description: float, dates: float, location: Location) -> Similarity:
    """Combine the four parts with the weights of ``dedup-v1``."""
    location_score = _LOCATION_SCORE[location]
    score = (
        TITLE_WEIGHT * title
        + DESCRIPTION_WEIGHT * description
        + DATE_WEIGHT * dates
        + LOCATION_WEIGHT * location_score
    )
    return Similarity(
        score=score,
        features={
            "title": title,
            "description": description,
            "dates": dates,
            "location": location,
            "location_score": location_score,
        },
    )


def decide(score: float, location: Location, *, same_source: bool) -> Decision:
    """Decide the link: ``auto``, ``possible`` (shown to the owner) or ``distinct``.

    Different places are different opportunities. Two listings of the same board are never linked
    automatically (several openings with identical text are legitimate).
    """
    if location == "none":
        return "distinct"
    if same_source:
        return "possible" if score >= SAME_SOURCE_POSSIBLE_THRESHOLD else "distinct"
    if score >= AUTO_THRESHOLD and location == "identical":
        return "auto"
    return "possible" if score >= POSSIBLE_THRESHOLD else "distinct"


@dataclass(frozen=True)
class PrimaryCandidate:
    """A listing that may become the primary one of an opportunity."""

    job_posting_id: int
    source_type: str
    first_seen_at: datetime


def choose_primary(candidates: Sequence[PrimaryCandidate]) -> int:
    """Return the primary listing: employer ATS first, then the earliest, then the lowest id."""
    best = min(
        candidates,
        key=lambda c: (c.source_type not in EMPLOYER_SOURCES, c.first_seen_at, c.job_posting_id),
    )
    return best.job_posting_id
