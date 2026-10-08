"""Company endpoints (document 07)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from jobs_radar.api.deps import get_company_service, get_inbox_default_intent
from jobs_radar.core.errors import InputValidationError
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.company import CompanyList, CompanySummary
from jobs_radar.services.companies import DEFAULT_RELEVANCE_MIN_SCORE, CompanyService

router = APIRouter(tags=["companies"])


@router.get("/companies", response_model=CompanyList)
async def list_companies(
    service: Annotated[CompanyService, Depends(get_company_service)],
    default_intent: Annotated[int | None, Depends(get_inbox_default_intent)],
    q: Annotated[str | None, Query(max_length=100)] = None,
    window: int = 15,
    sort: Literal["new", "relevant", "open", "name"] = "new",
    search_intent_id: Annotated[int | None, Query(ge=1)] = None,
    relevance_min_score: Annotated[int, Query(ge=0, le=100)] = DEFAULT_RELEVANCE_MIN_SCORE,
    relevant_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CompanyList:
    """List companies with new offers in the last 7, 15 or 30 days and the relevant subset."""
    if window not in (7, 15, 30):
        msg = "window must be 7, 15 or 30 days."
        raise InputValidationError(msg)
    intent_id = search_intent_id if search_intent_id is not None else default_intent
    page = await service.list_companies(
        LOCAL_OWNER_ID,
        q=q,
        window=window,
        sort=sort,
        search_intent_id=intent_id,
        relevance_min_score=relevance_min_score,
        relevant_only=relevant_only,
        limit=limit,
        offset=offset,
    )
    return CompanyList(
        items=[CompanySummary.model_validate(row, from_attributes=True) for row in page.rows],
        total=page.total,
        window=window,
        sort=sort,
        search_intent_id=intent_id,
        relevance_min_score=relevance_min_score,
    )
