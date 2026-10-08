"""CV proposal and review endpoints (document 07, sections 2 and 3)."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import (
    get_profile_service,
    get_proposal_service,
    get_review_service,
    get_session,
)
from jobs_radar.api.routes.profiles import profile_read
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.proposal import (
    ProposalItemRead,
    ProposalRead,
    ProposalRequest,
    ReviewRequest,
    ReviewResponse,
)
from jobs_radar.services.profiles import ProfileService
from jobs_radar.services.proposal_review import Decision, ReviewService
from jobs_radar.services.proposals import Consent, ProposalResult, ProposalService

router = APIRouter(tags=["proposals"])

Proposals = Annotated[ProposalService, Depends(get_proposal_service)]
Reviews = Annotated[ReviewService, Depends(get_review_service)]
Profiles = Annotated[ProfileService, Depends(get_profile_service)]
Session = Annotated[AsyncSession, Depends(get_session)]


def proposal_read(result: ProposalResult) -> ProposalRead:
    """Map a proposal and its items to the API model."""
    proposal = result.proposal
    return ProposalRead(
        profile_proposal_id=proposal.profile_proposal_id,
        career_profile_id=proposal.career_profile_id,
        document_id=proposal.document_id,
        provider_type=proposal.provider_type,
        provider_model=proposal.provider_model,
        prompt_version=proposal.prompt_version,
        redaction_policy=proposal.redaction_policy,
        consent=proposal.consent_json,
        status=proposal.status,
        completed_at=proposal.completed_at,
        created_at=proposal.created_at,
        items=[
            ProposalItemRead(
                proposal_item_id=i.proposal_item_id,
                path=i.path,
                value=i.value_json,
                source_excerpt=i.source_excerpt,
                confidence=i.confidence,
                review_status=i.review_status,
                edited_value=i.edited_value_json,
                reviewed_at=i.reviewed_at,
            )
            for i in result.items
        ],
    )


@router.post(
    "/documents/{document_id}/proposals",
    response_model=ProposalRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_proposal(
    document_id: int, body: ProposalRequest, service: Proposals, session: Session
) -> ProposalRead:
    """Ask the chosen model for profile proposals from the uploaded CV (needs consent if remote)."""
    consent = (
        Consent(body.consent.provider_connection_id, body.consent.model_id)
        if body.consent
        else None
    )
    result = await service.generate(
        LOCAL_OWNER_ID, document_id, body.career_profile_id, consent=consent
    )
    await session.commit()
    return proposal_read(result)


@router.get("/proposals/{profile_proposal_id}", response_model=ProposalRead)
async def get_proposal(profile_proposal_id: int, service: Proposals) -> ProposalRead:
    """Return a proposal with its field-level items."""
    return proposal_read(await service.get(LOCAL_OWNER_ID, profile_proposal_id))


@router.post("/profiles/{career_profile_id}/reviews", response_model=ReviewResponse)
async def review_proposal(
    career_profile_id: int,
    body: ReviewRequest,
    reviews: Reviews,
    proposals: Proposals,
    profiles: Profiles,
    session: Session,
) -> ReviewResponse:
    """Apply accept/edit/reject/defer decisions atomically (a revision if facts change)."""
    result = await reviews.review(
        LOCAL_OWNER_ID,
        career_profile_id,
        body.profile_proposal_id,
        [Decision(d.proposal_item_id, d.decision, d.value) for d in body.decisions],
        expected_current_revision=body.expected_current_revision,
        change_summary=body.change_summary,
    )
    profile = profile_read(await profiles.get(LOCAL_OWNER_ID, career_profile_id))
    proposal = proposal_read(
        await proposals.get(LOCAL_OWNER_ID, result.proposal.profile_proposal_id)
    )
    await session.commit()
    return ReviewResponse(created=result.created, profile=profile, proposal=proposal)
