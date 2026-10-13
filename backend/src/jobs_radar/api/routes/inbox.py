"""Inbox endpoints (document 07, section 5) and the owner's decisions on possible duplicates."""

from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_dedup_service, get_inbox_service, get_session
from jobs_radar.api.routes.evaluations import evaluation_read
from jobs_radar.db.models import InboxEvent
from jobs_radar.domain.enums import LOCAL_OWNER_ID, InboxAction
from jobs_radar.domain.matching.engine import band_of
from jobs_radar.schemas.evaluation import (
    DimensionQuality,
    DimensionStatus,
    FitBand,
    GateRead,
    RecommendationValue,
)
from jobs_radar.schemas.inbox import (
    ChangeRead,
    EvaluationBrief,
    InboxActionRequest,
    InboxActionResponse,
    InboxCounts,
    InboxEventRead,
    InboxItemDetail,
    InboxItemSummary,
    InboxList,
    InboxSort,
    InboxStateName,
    LinkDecisionResponse,
    SignalRead,
    SourceRef,
)
from jobs_radar.schemas.job_brief import JobBriefRead, TechnologyRead
from jobs_radar.services.dedup import DedupService
from jobs_radar.services.evaluation import EvaluationRecord
from jobs_radar.services.inbox import InboxFilters, InboxRowView, InboxService

router = APIRouter(tags=["inbox"])

Service = Annotated[InboxService, Depends(get_inbox_service)]
Session = Annotated[AsyncSession, Depends(get_session)]


def _brief(row: InboxRowView) -> EvaluationBrief | None:
    evaluation = row.evaluation
    if evaluation is None:
        return None
    return EvaluationBrief(
        match_evaluation_id=evaluation.match_evaluation_id,
        policy_version=evaluation.policy_version,
        fit_score=evaluation.fit_score,
        fit_band=cast(
            FitBand,
            band_of(evaluation.fit_score, gated=evaluation.recommendation == "not_recommended"),
        ),
        recommendation=cast(RecommendationValue, evaluation.recommendation),
        gates=[GateRead.model_validate(gate) for gate in evaluation.gates_json],
        profile_revision_id=evaluation.profile_revision_id,
        intent_revision_id=evaluation.intent_revision_id,
        created_at=evaluation.created_at,
    )


def summary(row: InboxRowView) -> InboxItemSummary:
    """Map an inbox row to its API model."""
    item = row.item
    sources = [
        SourceRef(
            job_posting_id=p.posting.job_posting_id,
            source_type=p.posting.source_type,
            source_name=p.source_display_name,
            url=p.posting.source_url,
            first_seen_at=p.posting.first_seen_at,
            closed=p.posting.closed_at is not None,
            job_opportunity_link_id=p.link.job_opportunity_link_id,
            link_state=cast(Any, p.link.state),
            similarity=float(p.link.similarity),
        )
        for p in row.postings
    ]
    return InboxItemSummary(
        job_inbox_item_id=item.job_inbox_item_id,
        job_opportunity_id=row.job_opportunity_id,
        job_posting_id=row.job_posting_id,
        state=cast(InboxStateName, item.state),
        is_shortlisted=item.is_shortlisted,
        version=item.version,
        title=row.title,
        company_name=row.company_name,
        locations=row.locations,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        closed=row.closed_at is not None,
        evaluated=row.evaluation is not None,
        evaluation=_brief(row),
        signals=[
            SignalRead(
                dimension_key=d.dimension_key,
                status=cast(DimensionStatus, d.status),
                quality=cast(DimensionQuality | None, d.quality),
                excluded=d.excluded,
            )
            for d in row.dimensions
        ],
        sources=sources,
        possible_duplicate=any(s.link_state == "possible" for s in sources),
        applied_at=item.applied_at,
        note=item.note,
    )


def _event(event: InboxEvent) -> InboxEventRead:
    return InboxEventRead(
        inbox_event_id=event.inbox_event_id,
        action=event.action,
        actor=cast(Any, event.actor),
        from_state=event.from_state,
        to_state=event.to_state,
        created_at=event.created_at,
    )


@router.get("/inbox", response_model=InboxList)
async def list_inbox(
    service: Service,
    state: Annotated[
        str, Query(pattern=r"^(all|to_review|unread|read|updated_unread|ignored|archived|applied)$")
    ] = "unread",
    shortlisted: bool | None = None,
    search_intent_id: Annotated[int | None, Query(ge=1)] = None,
    company: Annotated[str | None, Query(max_length=200)] = None,
    source: Annotated[str | None, Query(max_length=100)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    fit_min: Annotated[int | None, Query(ge=0, le=100)] = None,
    fit_max: Annotated[int | None, Query(ge=0, le=100)] = None,
    evaluated: bool | None = None,
    set_aside: bool | None = None,
    first_seen_from: Annotated[datetime | None, Query(alias="from")] = None,
    first_seen_to: Annotated[datetime | None, Query(alias="to")] = None,
    include_closed: bool = False,
    sort: InboxSort = "fit_desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
) -> InboxList:
    """Filter and sort the owner's inbox; scores come from the chosen (or first enabled) intent."""
    page = await service.list_items(
        LOCAL_OWNER_ID,
        InboxFilters(
            search_intent_id=search_intent_id,
            state=state,
            shortlisted=shortlisted,
            company=company,
            source=source,
            text=q,
            fit_min=fit_min,
            fit_max=fit_max,
            evaluated=evaluated,
            set_aside=set_aside,
            first_seen_from=first_seen_from,
            first_seen_to=first_seen_to,
            include_closed=include_closed,
            sort=sort,
        ),
        limit=limit,
        cursor=cursor,
    )
    return InboxList(
        items=[summary(row) for row in page.rows],
        next_cursor=page.next_cursor,
        counts=InboxCounts(**page.counts),
        search_intent_id=page.search_intent_id,
        set_aside_below_fit=page.set_aside_below_fit,
    )


@router.get("/inbox/{job_inbox_item_id}", response_model=InboxItemDetail)
async def get_inbox_item(
    job_inbox_item_id: int,
    service: Service,
    search_intent_id: Annotated[int | None, Query(ge=1)] = None,
) -> InboxItemDetail:
    """Return one item with its job text, evidence, sites and history."""
    detail = await service.detail(
        LOCAL_OWNER_ID, job_inbox_item_id, search_intent_id=search_intent_id
    )
    base = summary(detail.row)
    dimensions = (
        evaluation_read(EvaluationRecord(detail.row.evaluation, detail.dimensions)).dimensions
        if detail.row.evaluation
        else []
    )
    change = detail.last_change
    item = detail.row.item
    return InboxItemDetail(
        **base.model_dump(),
        description_text=detail.description,
        apply_url=detail.apply_url,
        read_at=item.read_at,
        ignore_reason=item.ignore_reason,
        application_url=item.application_url,
        dimensions=dimensions,
        events=[_event(e) for e in detail.events],
        brief=JobBriefRead(
            summary=detail.brief.summary,
            summary_model=detail.brief.summary_model,
            technologies=[TechnologyRead.model_validate(t) for t in detail.brief.technologies],
            facts=detail.brief.facts,
        ),
        last_change=(
            ChangeRead(changed_fields=list(change.changed_fields), created_at=change.created_at)
            if change
            else None
        ),
    )


@router.post("/inbox/{job_inbox_item_id}/actions", response_model=InboxActionResponse)
async def act_on_inbox_item(
    job_inbox_item_id: int,
    body: InboxActionRequest,
    service: Service,
    session: Session,
    search_intent_id: Annotated[int | None, Query(ge=1)] = None,
) -> InboxActionResponse:
    """Perform one validated action; a stale ``expected_version`` is a 409."""
    result = await service.act(
        LOCAL_OWNER_ID,
        job_inbox_item_id,
        InboxAction(body.action),
        expected_version=body.expected_version,
        reason=body.reason,
        note=body.note,
        applied_at=body.applied_at,
        application_url=str(body.application_url) if body.application_url else None,
    )
    await session.commit()
    # Read the item back through the detail query so it has the same shape as the list rows.
    detail = await service.detail(
        LOCAL_OWNER_ID, job_inbox_item_id, search_intent_id=search_intent_id
    )
    return InboxActionResponse(
        item=summary(detail.row), event=_event(result.event) if result.event else None
    )


@router.post(
    "/opportunity-links/{job_opportunity_link_id}/confirm", response_model=LinkDecisionResponse
)
async def confirm_link(
    job_opportunity_link_id: int,
    dedup: Annotated[DedupService, Depends(get_dedup_service)],
    session: Session,
) -> LinkDecisionResponse:
    """Confirm that two listings are the same opportunity."""
    link = await dedup.confirm(job_opportunity_link_id)
    await session.commit()
    return LinkDecisionResponse(job_opportunity_id=link.job_opportunity_id, state="confirmed")


@router.post(
    "/opportunity-links/{job_opportunity_link_id}/reject", response_model=LinkDecisionResponse
)
async def reject_link(
    job_opportunity_link_id: int,
    dedup: Annotated[DedupService, Depends(get_dedup_service)],
    session: Session,
) -> LinkDecisionResponse:
    """Say two listings are different: the listing gets an opportunity of its own."""
    opportunity = await dedup.reject(job_opportunity_link_id)
    await session.commit()
    return LinkDecisionResponse(job_opportunity_id=opportunity.job_opportunity_id, state="rejected")
