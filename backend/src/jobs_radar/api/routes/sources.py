"""Source configuration and collection-run endpoints (document 07)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.sources.catalogue import available_entries, get_entry
from jobs_radar.api.deps import (
    get_collection_service,
    get_location_scope_service,
    get_page_reader_proposal_service,
    get_session,
    get_source_service,
)
from jobs_radar.core.errors import InputValidationError
from jobs_radar.db.models import CollectionRun, SourceRunResult
from jobs_radar.domain.enums import (
    LOCAL_OWNER_ID,
    RunStatus,
    RunTrigger,
    SourceCategory,
    SourceOutcome,
    SourceType,
)
from jobs_radar.domain.sources import source_category
from jobs_radar.schemas.ai_settings import CredentialWrite
from jobs_radar.schemas.company_onboarding import (
    ReaderPostingRead,
    ReaderProposalRead,
    ReaderReplace,
)
from jobs_radar.schemas.source import (
    CatalogueEntryRead,
    CatalogueList,
    CollectionRunPage,
    CollectionRunRead,
    OnsiteAreaRead,
    SourceCreate,
    SourceList,
    SourcePreviewRead,
    SourcePreviewRequest,
    SourceRead,
    SourceResultRead,
    SourceScopeRead,
    SourceUpdate,
)
from jobs_radar.schemas.source_filters import JobBoardFilters
from jobs_radar.services.collection import CollectionService
from jobs_radar.services.location_scope import LocationScopeService
from jobs_radar.services.page_reader_proposal import PageReaderProposalService
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
        dropped_count=row.dropped_count,
        http_status=row.http_status,
        error_class=row.error_class,
        error_message=row.error_message,
        duration_ms=row.duration_ms,
    )


def _source(row: SourceStatusRow) -> SourceRead:
    source = row.source
    source_type = SourceType(source.source_type)
    category = source_category(source_type)
    entry = get_entry(source.external_identifier) if category is SourceCategory.JOB_BOARD else None
    if entry is None:
        credential_status = "not_needed"
    else:
        credential_status = (
            "not_needed"
            if not entry.requires_credential
            else ("saved" if source.credential_ciphertext else "none")
        )
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
        category=category,
        coverage_note=entry.coverage_note if entry else None,
        filters=(
            JobBoardFilters.model_validate(source.config_json or entry.default_filters.model_dump())
            if entry
            else (
                JobBoardFilters.model_validate(source.config_json) if source.config_json else None
            )
        ),
        credential_status=credential_status,
        credential_updated_at=source.credential_updated_at,
        terms_url=entry.terms_url if entry else None,
        attribution_text=entry.attribution_text if entry else None,
        next_run_allowed_at=row.next_run_allowed_at,
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


@router.get("/source-scope", response_model=SourceScopeRead)
async def get_source_scope(
    service: Annotated[LocationScopeService, Depends(get_location_scope_service)],
) -> SourceScopeRead:
    """Show where job boards look for postings: derived from the profile and the intents."""
    scope = await service.for_owner(LOCAL_OWNER_ID)
    return SourceScopeRead(
        configured=not scope.is_empty,
        country_codes=sorted(scope.country_codes),
        include_worldwide=scope.include_worldwide,
        any_country=scope.any_country,
        onsite_areas=[
            OnsiteAreaRead(place=area.place, radius_km=area.radius_km)
            for area in scope.onsite_areas
        ],
    )


@router.get("/source-catalogue", response_model=CatalogueList)
async def list_source_catalogue(
    service: Annotated[SourceService, Depends(get_source_service)],
) -> CatalogueList:
    """List the job boards that can be added, marking those already configured."""
    added = await service.added_types(LOCAL_OWNER_ID)
    return CatalogueList(
        items=[
            CatalogueEntryRead(
                catalogue_key=entry.catalogue_key,
                display_name=entry.display_name,
                coverage_note=entry.coverage_note,
                homepage_url=entry.homepage_url,
                requires_credential=entry.requires_credential,
                credential_label=entry.credential_label,
                terms_note=entry.terms_note,
                terms_url=entry.terms_url,
                terms_read_on=entry.terms_read_on,
                attribution_text=entry.attribution_text,
                delay_note=entry.delay_note,
                min_interval_minutes=entry.min_interval_minutes,
                default_filters=entry.default_filters,
                available_categories=list(entry.available_categories),
                already_added=entry.source_type in added,
            )
            for entry in available_entries()
        ]
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
        credential=body.credential,
        filters=body.filters,
        display_name=body.display_name,
    )
    await session.commit()
    return await _one(service, source.source_configuration_id)


@router.post("/sources/preview", response_model=SourcePreviewRead)
async def preview_source(
    body: SourcePreviewRequest,
    service: Annotated[SourceService, Depends(get_source_service)],
) -> SourcePreviewRead:
    """Count how many postings of a catalogue job board would be kept; nothing is saved."""
    entry, info = await service.preview(
        LOCAL_OWNER_ID, body.catalogue_key, credential=body.credential, filters=body.filters
    )
    return SourcePreviewRead(
        display_name=entry.display_name,
        postings_total=info.postings_count,
        postings_matching=info.matching_count or 0,
        matching_is_lower_bound=info.matching_is_lower_bound,
    )


@router.put("/sources/{source_configuration_id}/credential", response_model=SourceRead)
async def write_source_credential(
    source_configuration_id: int,
    body: CredentialWrite,
    service: Annotated[SourceService, Depends(get_source_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SourceRead:
    """Check and store a job board's key (write-only: only its status is ever returned)."""
    await service.set_credential(LOCAL_OWNER_ID, source_configuration_id, body.secret)
    await session.commit()
    return await _one(service, source_configuration_id)


@router.delete("/sources/{source_configuration_id}/credential", response_model=SourceRead)
async def delete_source_credential(
    source_configuration_id: int,
    service: Annotated[SourceService, Depends(get_source_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SourceRead:
    """Delete a job board's stored key; the board is disabled because it cannot run without it."""
    await service.clear_credential(LOCAL_OWNER_ID, source_configuration_id)
    await session.commit()
    return await _one(service, source_configuration_id)


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
        filters=body.filters,
        clear_filters=bool(body.clear_filters),
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


@router.post("/sources/{source_configuration_id}/reader/propose", response_model=ReaderProposalRead)
async def propose_source_reader(
    source_configuration_id: int,
    service: Annotated[SourceService, Depends(get_source_service)],
    proposals: Annotated[PageReaderProposalService, Depends(get_page_reader_proposal_service)],
) -> ReaderProposalRead:
    """Ask the local model for a new reader of a careers-page source (after ``schema_changed``)."""
    source = await service.get(LOCAL_OWNER_ID, source_configuration_id)
    if source.source_type != SourceType.PAGE_CONFIG.value:
        raise InputValidationError("Only a careers-page source has a reader.")
    proposal = await proposals.propose(LOCAL_OWNER_ID, source.url)
    return ReaderProposalRead(
        reader=proposal.config,
        preview=[
            ReaderPostingRead(title=p.title, url=p.url, location=p.location)
            for p in proposal.preview
        ],
        proposed_by=proposal.proposed_by,
    )


@router.put("/sources/{source_configuration_id}/reader", response_model=SourceRead)
async def approve_source_reader(
    source_configuration_id: int,
    body: ReaderReplace,
    service: Annotated[SourceService, Depends(get_source_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SourceRead:
    """Approve a new reader for a careers-page source; the previous one stays in the history."""
    await service.replace_page_reader(
        LOCAL_OWNER_ID,
        source_configuration_id,
        config=body.reader,
        proposed_by=body.proposed_by,
        expected_version=body.expected_version,
    )
    await session.commit()
    return await _one(service, source_configuration_id)
