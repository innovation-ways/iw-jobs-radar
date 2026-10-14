"""Company endpoints (document 07)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import (
    get_collection_service,
    get_company_onboarding_service,
    get_company_service,
    get_inbox_default_intent,
    get_page_reader_proposal_service,
    get_session,
)
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.repositories.schedule import ScheduleRepository
from jobs_radar.schemas.company import (
    CompanyFollowState,
    CompanyIgnoreState,
    CompanyList,
    CompanySummary,
)
from jobs_radar.schemas.company_onboarding import (
    DetectedBoardRead,
    OnboardingConfirm,
    OnboardingDetectionRead,
    OnboardingDetectRequest,
    OnboardingResultRead,
    ReaderPostingRead,
    ReaderProposalRead,
)
from jobs_radar.services.collection import CollectionService
from jobs_radar.services.companies import DEFAULT_RELEVANCE_MIN_SCORE, CompanyService
from jobs_radar.services.company_onboarding import CompanyOnboardingService
from jobs_radar.services.page_reader_proposal import PageReaderProposalService

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
    ignored_only: bool = False,
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
        ignored_only=ignored_only,
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


@router.post("/companies/onboarding/detect", response_model=OnboardingDetectionRead)
async def detect_company_boards(
    body: OnboardingDetectRequest,
    service: Annotated[CompanyOnboardingService, Depends(get_company_onboarding_service)],
) -> OnboardingDetectionRead:
    """Find out what a careers page can be collected from; nothing is saved (ADR-070)."""
    result = await service.detect(
        LOCAL_OWNER_ID,
        name=body.name,
        website_url=body.website_url,
        careers_url=body.careers_url,
    )
    return OnboardingDetectionRead(
        outcome=result.outcome,
        website_url=result.website_url,
        careers_url=result.careers_url,
        candidates=[
            DetectedBoardRead(
                source_type=c.source_type,
                identifier=c.identifier,
                display_name=c.display_name,
                postings_count=c.postings_count,
                layer=c.layer,
            )
            for c in result.candidates
        ],
        reason=result.reason,
        existing_company_id=result.existing_company_id,
    )


@router.post("/companies/onboarding", response_model=OnboardingResultRead, status_code=201)
async def follow_company_from_addresses(
    body: OnboardingConfirm,
    service: Annotated[CompanyOnboardingService, Depends(get_company_onboarding_service)],
    collection: Annotated[CollectionService, Depends(get_collection_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OnboardingResultRead:
    """Create the company, follow it and, with a chosen board, add it and queue its first run."""
    result = await service.confirm(
        LOCAL_OWNER_ID,
        name=body.name,
        website_url=body.website_url,
        careers_url=body.careers_url,
        source_type=body.source.source_type if body.source else None,
        identifier=body.source.identifier if body.source else None,
        filters_enabled=body.filters_enabled,
        reader=body.reader,
        reader_proposed_by=body.reader_proposed_by,
    )
    await session.commit()
    run_id: int | None = None
    if result.source is not None:
        # The worker executes it; the API only queues (ADR-042).
        run = await collection.request_run(
            LOCAL_OWNER_ID, source_configuration_id=result.source.source_configuration_id
        )
        run_id = run.collection_run_id
    return OnboardingResultRead(
        company_id=result.company.company_id,
        company_name=result.company.canonical_name,
        is_followed=True,
        source_configuration_id=result.source.source_configuration_id if result.source else None,
        collection_run_id=run_id,
        collecting=result.source is not None,
    )


@router.post("/companies/onboarding/propose-reader", response_model=ReaderProposalRead)
async def propose_careers_reader(
    body: OnboardingDetectRequest,
    onboarding: Annotated[CompanyOnboardingService, Depends(get_company_onboarding_service)],
    proposals: Annotated[PageReaderProposalService, Depends(get_page_reader_proposal_service)],
) -> ReaderProposalRead:
    """Ask the local model how to read a careers page that has no known board; nothing is saved."""
    _, careers = onboarding.addresses(body.website_url, body.careers_url)
    proposal = await proposals.propose(LOCAL_OWNER_ID, careers)
    return ReaderProposalRead(
        reader=proposal.config,
        preview=[
            ReaderPostingRead(title=p.title, url=p.url, location=p.location)
            for p in proposal.preview
        ],
        proposed_by=proposal.proposed_by,
    )
