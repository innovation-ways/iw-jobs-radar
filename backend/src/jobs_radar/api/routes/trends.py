"""Trend endpoints (document 07)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_inbox_default_intent, get_session, get_trend_service
from jobs_radar.core.errors import NotFoundError
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.trends import TermKind, TrendReportRead
from jobs_radar.services.trends import TrendReport, TrendService

router = APIRouter(tags=["trends"])

Service = Annotated[TrendService, Depends(get_trend_service)]
DefaultIntent = Annotated[int | None, Depends(get_inbox_default_intent)]
Session = Annotated[AsyncSession, Depends(get_session)]


def report_read(report: TrendReport) -> TrendReportRead:
    """Map a trend report to its API model."""
    return TrendReportRead.model_validate(
        {
            "kind": report.kind,
            "search_intent_id": report.search_intent_id,
            "relevance_min_score": report.relevance_min_score,
            "available_weeks": report.available_weeks,
            "first_week": report.first_week,
            "periods": report.periods,
            "weeks": report.weeks,
            "rows": report.rows,
            "intent_revision_changes": report.intent_revision_changes,
            "source_set_changes": report.source_set_changes,
        },
        from_attributes=True,
    )


@router.get("/trends", response_model=TrendReportRead)
async def get_trends(
    service: Service,
    default_intent: DefaultIntent,
    kind: TermKind,
    weeks: Annotated[int, Query(ge=1, le=52)] = 12,
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
    search_intent_id: Annotated[int | None, Query(ge=1)] = None,
) -> TrendReportRead:
    """Ranked terms of relevant jobs with weekly series, shares, markers and locked periods."""
    intent = search_intent_id if search_intent_id is not None else default_intent
    if intent is None:
        msg = "Create a search intent first: trends cover the jobs that are relevant to it."
        raise NotFoundError(msg)
    return report_read(
        await service.report(LOCAL_OWNER_ID, intent, kind=kind, weeks=weeks, limit=limit)
    )


@router.post("/trends/recompute", status_code=202)
async def recompute_trends(
    service: Service,
    default_intent: DefaultIntent,
    session: Session,
    search_intent_id: Annotated[int | None, Query(ge=1)] = None,
) -> dict[str, int]:
    """Compute the weekly aggregates now (the worker also does it daily)."""
    intent = search_intent_id if search_intent_id is not None else default_intent
    if intent is None:
        msg = "Create a search intent first."
        raise NotFoundError(msg)
    written = await service.recompute(LOCAL_OWNER_ID, intent)
    await session.commit()
    return {"rows": written}
