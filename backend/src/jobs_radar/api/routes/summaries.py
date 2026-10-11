"""Job-summary endpoint (ADR-059): write the summary of one job on demand."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_session, get_summary_assess_service
from jobs_radar.schemas.job_brief import SummaryResponse
from jobs_radar.services.summary_assess import SummaryAssessService

router = APIRouter(tags=["summaries"])

Service = Annotated[SummaryAssessService, Depends(get_summary_assess_service)]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/jobs/{job_posting_id}/summary", response_model=SummaryResponse)
async def write_summary(job_posting_id: int, service: Service, session: Session) -> SummaryResponse:
    """Write (or return the stored) AI summary of a job with the local model.

    The worker summarises new jobs by itself; this is how an older one gets its summary.
    """
    result = await service.summarise(job_posting_id)
    await session.commit()
    assert result.text is not None  # noqa: S101  # the service raises when no summary was written
    return SummaryResponse(summary=result.text, created=result.created)
