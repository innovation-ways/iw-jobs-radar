"""Source configuration and collection-run endpoints (document 07)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import (
    get_collection_service,
    get_session,
    get_source_service,
)
from jobs_radar.db.models import CollectionRun, SourceRunResult
from jobs_radar.domain.enums import LOCAL_OWNER_ID, RunStatus, RunTrigger, SourceOutcome, SourceType
from jobs_radar.schemas.source import (
    CollectionRunPage,
    CollectionRunRead,
    SourceCreate,
    SourceList,
    SourceRead,
    SourceResultRead,
    SourceUpdate,
)
from jobs_radar.services.collection import CollectionService
from jobs_radar.services.sources import SourceService, SourceStatusRow

router = APIRouter(tags=["sources"])


def _result(row: SourceRunResult) -> SourceResultRead:
    return SourceResultRead(
        collection_run_id=row.collection_run_id,
        source_configuration_id=row.source_configuration_id,
        outcome=SourceOutcome(row.outcome),
        started_at=row.started_at,
        finished_at=row.finished_at,
        collected_count=row.collected_count,
        new_count=row.new_count,
        updated_count=row.updated_count,
        deduplicated_count=row.deduplicated_count,
        closed_count=row.closed_count,
        http_status=row.http_status,
        error_class=row.error_class,
        error_message=row.error_message,
        duration_ms=row.duration_ms,
    )


def _source(row: SourceStatusRow) -> SourceRead:
    source = row.source
    return SourceRead(
        source_configuration_id=source.source_configuration_id,
        source_type=SourceType(source.source_type),
        external_identifier=source.external_identifier,
        display_name=source.display_name,
        company_id=source.company_id,
        company_name=row.company_name,
        url=source.url,
        enabled=source.enabled,
        rate_limit_per_minute=source.rate_limit_per_minute,
        version=source.version,
        open_postings=row.open_postings,
        last_result=_result(row.last_result) if row.last_result else None,
    )


def _run(run: CollectionRun, results: list[SourceRunResult]) -> CollectionRunRead:
    return CollectionRunRead(
        collection_run_id=run.collection_run_id,
        source_configuration_id=run.source_configuration_id,
        trigger=RunTrigger(run.trigger),
        status=RunStatus(run.status),
        requested_at=run.requested_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_class=run.error_class,
        results=[_result(item) for item in results],
    )


async def _one(service: SourceService, source_configuration_id: int) -> SourceRead:
    rows = await service.list_with_status(LOCAL_OWNER_ID)
    return _source(
        next(r for r in rows if r.source.source_configuration_id == source_configuration_id)
    )


@router.get("/sources", response_model=SourceList)
async def list_sources(
    service: Annotated[SourceService, Depends(get_source_service)],
) -> SourceList:
    """List configured sources with their latest status."""
    return SourceList(
        items=[_source(row) for row in await service.list_with_status(LOCAL_OWNER_ID)]
    )


@router.post("/sources", response_model=SourceRead, status_code=201)
async def create_source(
    body: SourceCreate,
    service: Annotated[SourceService, Depends(get_source_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SourceRead:
    """Validate a board against the real source and add it (and its company)."""
    source = await service.add(
        owner_id=LOCAL_OWNER_ID,
        source_type=body.source_type,
        identifier=body.external_identifier,
        enabled=body.enabled,
    )
    await session.commit()
    return await _one(service, source.source_configuration_id)


@router.put("/sources/{source_configuration_id}", response_model=SourceRead)
async def update_source(
    source_configuration_id: int,
    body: SourceUpdate,
    service: Annotated[SourceService, Depends(get_source_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SourceRead:
    """Change the enabled flag or rate limit of a source."""
    await service.update(
        LOCAL_OWNER_ID,
        source_configuration_id,
        expected_version=body.expected_version,
        enabled=body.enabled,
        rate_limit_per_minute=body.rate_limit_per_minute,
    )
    await session.commit()
    return await _one(service, source_configuration_id)


async def _queue(
    collection: CollectionService, source_configuration_id: int | None
) -> CollectionRunRead:
    """Queue a run; the worker executes it (the API never runs collection)."""
    run = await collection.request_run(
        LOCAL_OWNER_ID, source_configuration_id=source_configuration_id
    )
    return _run(run, [])


@router.post(
    "/sources/{source_configuration_id}/run", response_model=CollectionRunRead, status_code=202
)
async def run_source(
    source_configuration_id: int,
    collection: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionRunRead:
    """Queue a manual run of one source (even if it is disabled)."""
    return await _queue(collection, source_configuration_id)


@router.post("/collection-runs", response_model=CollectionRunRead, status_code=202)
async def run_all_sources(
    collection: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionRunRead:
    """Queue a run of every enabled source."""
    return await _queue(collection, None)


@router.get("/collection-runs", response_model=CollectionRunPage)
async def list_collection_runs(
    collection: Annotated[CollectionService, Depends(get_collection_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before_collection_run_id: Annotated[int | None, Query(ge=1)] = None,
) -> CollectionRunPage:
    """List run history, newest first, with per-source outcomes."""
    page, cursor = await collection.list_runs(
        LOCAL_OWNER_ID, limit=limit, before_id=before_collection_run_id
    )
    return CollectionRunPage(
        items=[_run(run, results) for run, results in page], next_before_collection_run_id=cursor
    )
