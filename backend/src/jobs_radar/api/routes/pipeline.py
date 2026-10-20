"""Pipeline status: how the worker is doing (read-only)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_pipeline_service, get_reextraction_service, get_session
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.pipeline import (
    PipelineStatusRead,
    ReextractionPreviewRead,
    ReextractionQueuedRead,
    ReextractionRequest,
)
from jobs_radar.services.pipeline import PipelineService
from jobs_radar.services.reextraction import ReextractionService

router = APIRouter(tags=["pipeline"])

Service = Annotated[PipelineService, Depends(get_pipeline_service)]


@router.get("/pipeline/status", response_model=PipelineStatusRead)
async def pipeline_status(
    service: Service,
    search_intent_id: Annotated[int | None, Query(ge=1)] = None,
) -> PipelineStatusRead:
    """Analysis and scoring progress, pace, time left, failures and the worker's state."""
    return await service.status(LOCAL_OWNER_ID, intent_id=search_intent_id)


Reextraction = Annotated[ReextractionService, Depends(get_reextraction_service)]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/pipeline/re-extraction", response_model=ReextractionPreviewRead)
async def preview_reextraction(
    service: Reextraction, since_days: Annotated[int, Query(ge=1, le=365)] = 30
) -> ReextractionPreviewRead:
    """Count the open jobs that the current prompt would analyse again; changes nothing."""
    preview = await service.preview(LOCAL_OWNER_ID, since_days)
    return ReextractionPreviewRead(
        candidates=preview.candidates,
        model=preview.model,
        seconds_per_job=preview.seconds_per_job,
        minutes=preview.minutes,
    )


@router.post("/pipeline/re-extraction", response_model=ReextractionQueuedRead)
async def queue_reextraction(
    body: ReextractionRequest, service: Reextraction, session: Session
) -> ReextractionQueuedRead:
    """Queue those analyses; the worker takes them like any other. Repeating it queues nothing."""
    queued = await service.queue(LOCAL_OWNER_ID, body.since_days)
    await session.commit()
    return ReextractionQueuedRead(queued=queued)
