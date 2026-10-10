"""Career-direction endpoints (ADR-057): assess one job against the owner's directions."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_direction_assess_service, get_session
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.direction import AssessResponse
from jobs_radar.services.direction_assess import DirectionAssessService

router = APIRouter(tags=["directions"])

Service = Annotated[DirectionAssessService, Depends(get_direction_assess_service)]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/jobs/{job_posting_id}/assess-directions", response_model=AssessResponse)
async def assess_directions(
    job_posting_id: int, service: Service, session: Session
) -> AssessResponse:
    """Judge a job against every enabled direction with the local model and score it again.

    Older jobs are never judged in bulk; this is how one of them is assessed on demand.
    """
    summary = await service.assess(LOCAL_OWNER_ID, job_posting_id)
    await session.commit()
    return AssessResponse(judged=summary.judged, evaluated=summary.evaluated)
