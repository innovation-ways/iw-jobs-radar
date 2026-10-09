"""Pipeline status: how the worker is doing (read-only)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from jobs_radar.api.deps import get_pipeline_service
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.pipeline import PipelineStatusRead
from jobs_radar.services.pipeline import PipelineService

router = APIRouter(tags=["pipeline"])

Service = Annotated[PipelineService, Depends(get_pipeline_service)]


@router.get("/pipeline/status", response_model=PipelineStatusRead)
async def pipeline_status(
    service: Service,
    search_intent_id: Annotated[int | None, Query(ge=1)] = None,
) -> PipelineStatusRead:
    """Analysis and scoring progress, pace, time left, failures and the worker's state."""
    return await service.status(LOCAL_OWNER_ID, intent_id=search_intent_id)
