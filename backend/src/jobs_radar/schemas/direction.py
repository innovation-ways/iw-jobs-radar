"""API models for career directions (ADR-057)."""

from jobs_radar.schemas.common import StrictModel


class AssessResponse(StrictModel):
    """What assessing one job did: judgements made and new evaluations stored."""

    judged: int
    evaluated: int
