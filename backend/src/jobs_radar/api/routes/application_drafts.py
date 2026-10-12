"""Pre-application endpoints (ADR-064): write a draft for one job on request, list the drafts."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_application_draft_service, get_session
from jobs_radar.db.models import ApplicationDraft
from jobs_radar.schemas.application_draft import (
    ApplicationContent,
    ApplicationDraftList,
    ApplicationDraftRead,
)
from jobs_radar.services.application_draft import ApplicationDraftService

router = APIRouter(tags=["application-drafts"])

Service = Annotated[ApplicationDraftService, Depends(get_application_draft_service)]
Session = Annotated[AsyncSession, Depends(get_session)]


def _read(row: ApplicationDraft) -> ApplicationDraftRead:
    return ApplicationDraftRead(
        application_draft_id=row.application_draft_id,
        created_at=row.created_at,
        model=row.model,
        prompt_version=row.prompt_version,
        draft=ApplicationContent.model_validate(row.draft_json),
    )


@router.post("/jobs/{job_posting_id}/application-draft", response_model=ApplicationDraftRead)
async def write_draft(
    job_posting_id: int, service: Service, session: Session
) -> ApplicationDraftRead:
    """Write a new pre-application draft of a job with the local model and keep it.

    Never automatic: the owner asks, so the profile facts reach the model only on request.
    """
    row = await service.generate(job_posting_id)
    await session.commit()
    return _read(row)


@router.get("/jobs/{job_posting_id}/application-drafts", response_model=ApplicationDraftList)
async def list_drafts(job_posting_id: int, service: Service) -> ApplicationDraftList:
    """List the drafts written for a job, newest first."""
    return ApplicationDraftList(items=[_read(r) for r in await service.list_drafts(job_posting_id)])
