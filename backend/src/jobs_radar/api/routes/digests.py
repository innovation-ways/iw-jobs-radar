"""Daily digest endpoint (document 07, section 5)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_session
from jobs_radar.api.routes.inbox import summary
from jobs_radar.api.routes.sources import _run
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.repositories.runs import RunRepository
from jobs_radar.schemas.digest import (
    ChangedItemRead,
    DigestCounts,
    DigestRead,
    SourceHealthRead,
)
from jobs_radar.services.digest import DigestService

router = APIRouter(tags=["digests"])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/digests/daily", response_model=DigestRead)
async def daily_digest(
    session: Session, search_intent_id: Annotated[int | None, Query(ge=1)] = None
) -> DigestRead:
    """Return new high-fit opportunities, changed shortlisted jobs and sources needing attention."""
    digest = await DigestService(session).build(LOCAL_OWNER_ID, search_intent_id=search_intent_id)
    last_run = None
    if digest.last_run is not None:
        results = await RunRepository(session).results_for([digest.last_run.collection_run_id])
        last_run = _run(digest.last_run, results[digest.last_run.collection_run_id])
    return DigestRead(
        generated_at=digest.generated_at,
        since=digest.since,
        search_intent_id=digest.search_intent_id,
        alert_threshold=digest.alert_threshold,
        new_high_fit=[summary(row) for row in digest.new_high_fit],
        changed_shortlisted=[
            ChangedItemRead(
                item=summary(c.row), changed_fields=c.changed_fields, changed_at=c.changed_at
            )
            for c in digest.changed_shortlisted
        ],
        source_health=[
            SourceHealthRead(
                source_configuration_id=h.source_configuration_id,
                display_name=h.display_name,
                status=h.status,
                error_class=h.error_class,
                error_message=h.error_message,
                last_run_at=h.last_run_at,
            )
            for h in digest.source_health
        ],
        last_run=last_run,
        counts=DigestCounts(**digest.counts),
    )
