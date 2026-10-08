"""Evaluation endpoints (document 07, section 5): score a job, read a score, re-score an intent."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_evaluation_service, get_session
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.domain.matching.engine import band_of
from jobs_radar.schemas.evaluation import (
    DimensionQuality,
    DimensionRead,
    DimensionStatus,
    EvaluationRead,
    EvaluationRequest,
    FitBand,
    GateRead,
    RecommendationValue,
    RescoreResponse,
)
from jobs_radar.services.evaluation import EvaluationRecord, EvaluationService

router = APIRouter(tags=["evaluations"])

Service = Annotated[EvaluationService, Depends(get_evaluation_service)]
Session = Annotated[AsyncSession, Depends(get_session)]


def evaluation_read(record: EvaluationRecord) -> EvaluationRead:
    """Map a stored evaluation to its API model."""
    evaluation = record.evaluation
    gated = evaluation.recommendation == "not_recommended"
    return EvaluationRead(
        match_evaluation_id=evaluation.match_evaluation_id,
        job_snapshot_id=evaluation.job_snapshot_id,
        job_extraction_id=evaluation.job_extraction_id,
        profile_revision_id=evaluation.profile_revision_id,
        intent_revision_id=evaluation.intent_revision_id,
        policy_version=evaluation.policy_version,
        job_source_hash=evaluation.job_source_hash,
        fit_score=evaluation.fit_score,
        fit_band=cast(FitBand, band_of(evaluation.fit_score, gated=gated)),
        recommendation=cast(RecommendationValue, evaluation.recommendation),
        gates=[GateRead.model_validate(gate) for gate in evaluation.gates_json],
        weights=evaluation.weights_json,
        dimensions=[
            DimensionRead(
                dimension_key=d.dimension_key,
                status=cast(DimensionStatus, d.status),
                quality=cast(DimensionQuality | None, d.quality),
                weight=d.weight,
                effective_weight=float(d.effective_weight),
                strength=float(d.strength),
                contribution=float(d.contribution),
                excluded=d.excluded,
                evidence=d.evidence_json,
                explanation=d.explanation,
            )
            for d in record.dimensions
        ],
        created_at=evaluation.created_at,
    )


@router.post("/jobs/{job_posting_id}/evaluations", response_model=EvaluationRead, status_code=201)
async def evaluate_job(
    job_posting_id: int,
    body: EvaluationRequest,
    service: Service,
    session: Session,
    response: Response,
) -> EvaluationRead:
    """Score a job's latest extraction under exact revisions (no AI is called here)."""
    record = await service.evaluate_posting(
        LOCAL_OWNER_ID,
        job_posting_id,
        profile_revision_id=body.profile_revision_id,
        intent_revision_id=body.intent_revision_id,
    )
    await session.commit()
    if not record.created:
        response.status_code = 200  # the same inputs were already evaluated
    return evaluation_read(record)


@router.get("/evaluations/{match_evaluation_id}", response_model=EvaluationRead)
async def get_evaluation(match_evaluation_id: int, service: Service) -> EvaluationRead:
    """Return a stored evaluation: score, policy version, dimensions and evidence."""
    return evaluation_read(await service.get(LOCAL_OWNER_ID, match_evaluation_id))


@router.post("/intents/{search_intent_id}/rescore", response_model=RescoreResponse)
async def rescore_intent(
    search_intent_id: int, service: Service, session: Session
) -> RescoreResponse:
    """Score existing jobs again under the intent's current revision, using stored AI results."""
    summary = await service.rescore(LOCAL_OWNER_ID, search_intent_id)
    await session.commit()
    return RescoreResponse(evaluated=summary.evaluated, skipped=summary.skipped)
