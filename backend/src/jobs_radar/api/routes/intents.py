"""Search intent endpoints (document 07, section 4) and the taxonomy listing."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_intent_service, get_session, get_taxonomy_service
from jobs_radar.db.models import IntentRevision
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.intent_api import (
    IntentCreate,
    IntentList,
    IntentRead,
    IntentRevisionList,
    IntentRevisionRead,
    IntentSave,
    IntentSaveResponse,
    TaxonomyGroup,
    TaxonomyRead,
    TaxonomyReplacement,
    TaxonomyTermRead,
    VersionRequest,
)
from jobs_radar.schemas.profile_api import RestoreRequest
from jobs_radar.services.intents import IntentService, IntentView
from jobs_radar.services.taxonomy import TaxonomyService

router = APIRouter(tags=["intents"])

Service = Annotated[IntentService, Depends(get_intent_service)]
Session = Annotated[AsyncSession, Depends(get_session)]


def _revision(revision: IntentRevision) -> IntentRevisionRead:
    return IntentRevisionRead(
        intent_revision_id=revision.intent_revision_id,
        revision_number=revision.revision_number,
        created_at=revision.created_at,
        change_summary=revision.change_summary,
        definition=IntentDefinition.model_validate(revision.intent_json),
    )


def intent_read(view: IntentView) -> IntentRead:
    """Map an intent view to its API model."""
    intent = view.intent
    return IntentRead(
        search_intent_id=intent.search_intent_id,
        career_profile_id=intent.career_profile_id,
        title=intent.title,
        enabled=intent.enabled,
        version=intent.version,
        current_revision=_revision(view.current) if view.current else None,
    )


@router.post("/profiles/{career_profile_id}/intents", response_model=IntentRead, status_code=201)
async def create_intent(
    career_profile_id: int, body: IntentCreate, service: Service, session: Session
) -> IntentRead:
    """Create an intent and its revision 1."""
    definition = IntentDefinition.model_validate(body.model_dump(exclude={"enabled"}))
    view = await service.create(LOCAL_OWNER_ID, career_profile_id, definition, enabled=body.enabled)
    await session.commit()
    return intent_read(view)


@router.get("/profiles/{career_profile_id}/intents", response_model=IntentList)
async def list_intents(career_profile_id: int, service: Service) -> IntentList:
    """List a profile's intents with their current revisions."""
    views = await service.list_for_profile(LOCAL_OWNER_ID, career_profile_id)
    return IntentList(items=[intent_read(view) for view in views])


@router.put("/intents/{search_intent_id}", response_model=IntentSaveResponse)
async def save_intent(
    search_intent_id: int, body: IntentSave, service: Service, session: Session
) -> IntentSaveResponse:
    """Save the intent as its next immutable revision (no revision when nothing changed)."""
    definition = IntentDefinition.model_validate(
        body.model_dump(exclude={"expected_current_revision", "change_summary"})
    )
    result = await service.save(
        LOCAL_OWNER_ID,
        search_intent_id,
        definition,
        expected_current_revision=body.expected_current_revision,
        change_summary=body.change_summary,
    )
    await session.commit()
    return IntentSaveResponse(created=result.created, intent=intent_read(result.view))


@router.post("/intents/{search_intent_id}/enable", response_model=IntentRead)
async def enable_intent(
    search_intent_id: int, body: VersionRequest, service: Service, session: Session
) -> IntentRead:
    """Enable the intent."""
    view = await service.set_enabled(
        LOCAL_OWNER_ID, search_intent_id, enabled=True, expected_version=body.expected_version
    )
    await session.commit()
    return intent_read(view)


@router.post("/intents/{search_intent_id}/disable", response_model=IntentRead)
async def disable_intent(
    search_intent_id: int, body: VersionRequest, service: Service, session: Session
) -> IntentRead:
    """Disable the intent."""
    view = await service.set_enabled(
        LOCAL_OWNER_ID, search_intent_id, enabled=False, expected_version=body.expected_version
    )
    await session.commit()
    return intent_read(view)


@router.get("/intents/{search_intent_id}/revisions", response_model=IntentRevisionList)
async def list_intent_revisions(search_intent_id: int, service: Service) -> IntentRevisionList:
    """List the intent's immutable revisions, newest first."""
    revisions = await service.revisions(LOCAL_OWNER_ID, search_intent_id)
    return IntentRevisionList(items=[_revision(revision) for revision in revisions])


@router.get(
    "/intents/{search_intent_id}/revisions/{intent_revision_id}",
    response_model=IntentRevisionRead,
)
async def get_intent_revision(
    search_intent_id: int, intent_revision_id: int, service: Service
) -> IntentRevisionRead:
    """Return one intent revision."""
    return _revision(await service.revision(LOCAL_OWNER_ID, search_intent_id, intent_revision_id))


@router.post(
    "/intents/{search_intent_id}/revisions/{intent_revision_id}/restore",
    response_model=IntentSaveResponse,
)
async def restore_intent_revision(
    search_intent_id: int,
    intent_revision_id: int,
    body: RestoreRequest,
    service: Service,
    session: Session,
) -> IntentSaveResponse:
    """Make an old revision's content the next revision."""
    result = await service.restore(
        LOCAL_OWNER_ID,
        search_intent_id,
        intent_revision_id,
        expected_current_revision=body.expected_current_revision,
    )
    await session.commit()
    return IntentSaveResponse(created=result.created, intent=intent_read(result.view))


@router.get("/taxonomy", response_model=TaxonomyRead)
async def get_taxonomy(
    service: Annotated[TaxonomyService, Depends(get_taxonomy_service)],
) -> TaxonomyRead:
    """List the controlled vocabularies the intent's stance controls are built from."""
    groups = await service.groups()
    return TaxonomyRead(
        groups=[
            TaxonomyGroup(
                kind=kind,
                terms=[TaxonomyTermRead(term_key=t.term_key, label=t.label) for t in terms],
            )
            for kind, terms in groups.items()
        ],
        replacements=[
            TaxonomyReplacement(kind=kind, from_key=old, to_key=new)
            for kind, merged in (await service.replacements()).items()
            for old, new in merged.items()
        ],
    )
