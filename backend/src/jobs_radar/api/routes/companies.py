"""Company endpoints (document 07)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_company_service, get_inbox_default_intent, get_session
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.repositories.schedule import ScheduleRepository
from jobs_radar.schemas.company import (
    CompanyFollowState,
    CompanyIgnoreState,
    CompanyList,
    CompanySummary,
)
from jobs_radar.services.companies import DEFAULT_RELEVANCE_MIN_SCORE, CompanyService

router = APIRouter(tags=["companies"])


@router.get("/companies", response_model=CompanyList)
async def list_companies(
    service: Annotated[CompanyService, Depends(get_company_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
    default_intent: Annotated[int | None, Depends(get_inbox_default_intent)],
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: Literal["newest", "recommended", "fit", "name"] = "newest",
    search_intent_id: Annotated[int | None, Query(ge=1)] = None,
    relevance_min_score: Annotated[int, Query(ge=0, le=100)] = DEFAULT_RELEVANCE_MIN_SCORE,
    followed_only: bool = False,
    hide_ignored: bool = False,
    open_only: bool = False,
    recommended_only: bool = False,
    pending_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CompanyList:
    """List companies: followed first, then by the best fit of their counted offers."""
    intent_id = search_intent_id if search_intent_id is not None else default_intent
    page = await service.list_companies(
        LOCAL_OWNER_ID,
        q=q,
        sort=sort,
        search_intent_id=intent_id,
        relevance_min_score=relevance_min_score,
        followed_only=followed_only,
        hide_ignored=hide_ignored,
        open_only=open_only,
        recommended_only=recommended_only,
        pending_only=pending_only,
        limit=limit,
        offset=offset,
    )
    return CompanyList(
        items=[CompanySummary.model_validate(row, from_attributes=True) for row in page.rows],
        total=page.total,
        sort=sort,
        search_intent_id=intent_id,
        relevance_min_score=relevance_min_score,
        recency_days=await ScheduleRepository(session).company_recency_days(LOCAL_OWNER_ID),
    )


@router.put("/companies/{company_id}/follow", response_model=CompanyFollowState)
async def follow_company(
    company_id: int,
    service: Annotated[CompanyService, Depends(get_company_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CompanyFollowState:
    """Follow a company (idempotent)."""
    await service.set_followed(LOCAL_OWNER_ID, company_id, followed=True)
    await session.commit()
    return CompanyFollowState(company_id=company_id, is_followed=True)


@router.delete("/companies/{company_id}/follow", response_model=CompanyFollowState)
async def unfollow_company(
    company_id: int,
    service: Annotated[CompanyService, Depends(get_company_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CompanyFollowState:
    """Stop following a company (idempotent)."""
    await service.set_followed(LOCAL_OWNER_ID, company_id, followed=False)
    await session.commit()
    return CompanyFollowState(company_id=company_id, is_followed=False)


@router.put("/companies/{company_id}/ignore", response_model=CompanyIgnoreState)
async def ignore_company(
    company_id: int,
    service: Annotated[CompanyService, Depends(get_company_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CompanyIgnoreState:
    """Ignore a company: its open offers move to Ignored at once (idempotent, ADR-061)."""
    await service.set_ignored(LOCAL_OWNER_ID, company_id, ignored=True)
    await session.commit()
    return CompanyIgnoreState(company_id=company_id, is_ignored=True)


@router.delete("/companies/{company_id}/ignore", response_model=CompanyIgnoreState)
async def unignore_company(
    company_id: int,
    service: Annotated[CompanyService, Depends(get_company_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CompanyIgnoreState:
    """Stop ignoring a company: restores the offers that ignoring moved (idempotent)."""
    await service.set_ignored(LOCAL_OWNER_ID, company_id, ignored=False)
    await session.commit()
    return CompanyIgnoreState(company_id=company_id, is_ignored=False)
