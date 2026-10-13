"""Summary for a dashboard widget such as Homepage's ``customapi`` (ADR-065)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from jobs_radar.api.deps import get_inbox_service, get_readiness_service
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.inbox import WidgetSummaryRead
from jobs_radar.services.inbox import InboxService
from jobs_radar.services.readiness import ReadinessService

router = APIRouter(tags=["widget"])


@router.get("/widget/summary", response_model=WidgetSummaryRead)
async def widget_summary(
    inbox: Annotated[InboxService, Depends(get_inbox_service)],
    readiness: Annotated[ReadinessService, Depends(get_readiness_service)],
    fit_min: Annotated[int, Query(ge=0, le=100)] = 65,
    search_intent_id: Annotated[int | None, Query(ge=1)] = None,
) -> WidgetSummaryRead:
    """Return the jobs to review, those at or above ``fit_min`` and whether the stack is ready.

    Always answers 200 so the widget can show the state; ``/readyz`` is the probe for monitors.
    """
    summary = await inbox.widget_summary(LOCAL_OWNER_ID, fit_min, search_intent_id)
    report = await readiness.check()
    return WidgetSummaryRead(
        to_review=summary.to_review,
        to_review_high_fit=summary.to_review_high_fit,
        fit_threshold=fit_min,
        best_fit=summary.best_fit,
        unread_total=summary.unread_total,
        followed_recommended=summary.followed_recommended,
        status="ready" if report.ready else "unavailable",
        components={"database": report.database.value, "worker": report.worker.value},
    )
