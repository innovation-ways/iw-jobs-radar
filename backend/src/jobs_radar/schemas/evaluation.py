"""API contracts for evaluations (document 07, section 5)."""

from datetime import datetime
from typing import Any, Literal

from jobs_radar.schemas.common import StrictModel

FitBand = Literal["excellent", "strong", "average", "low", "not_recommended"]
RecommendationValue = Literal["recommended", "not_recommended"]
DimensionStatus = Literal["match", "mismatch", "unknown"]
DimensionQuality = Literal["strong", "partial", "weak"]


class EvaluationRequest(StrictModel):
    """Evaluate a job under exact profile and intent revisions."""

    profile_revision_id: int
    intent_revision_id: int
    policy_version: Literal["matching-v1.8"] = "matching-v1.8"


class GateRead(StrictModel):
    """A hard constraint that fired."""

    code: str
    reason: str
    evidence: dict[str, Any]


class DimensionRead(StrictModel):
    """How one dimension scored, with its evidence."""

    dimension_key: str
    status: DimensionStatus
    quality: DimensionQuality | None
    weight: int
    effective_weight: float
    strength: float
    contribution: float
    excluded: bool
    evidence: dict[str, Any]
    explanation: str


class EvaluationRead(StrictModel):
    """An immutable evaluation: the score and everything it was computed from."""

    match_evaluation_id: int
    job_snapshot_id: int
    job_extraction_id: int
    profile_revision_id: int
    intent_revision_id: int
    policy_version: str
    job_source_hash: str
    fit_score: int
    fit_band: FitBand
    recommendation: RecommendationValue
    gates: list[GateRead]
    weights: dict[str, int]
    dimensions: list[DimensionRead]
    created_at: datetime


class RescoreResponse(StrictModel):
    """How many existing jobs were scored again under the intent's current revision."""

    evaluated: int
    skipped: int
