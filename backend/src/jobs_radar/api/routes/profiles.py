"""Career profile endpoints (document 07, section 2) and the portable export."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import (
    get_intent_service,
    get_profile_data_service,
    get_profile_service,
    get_session,
)
from jobs_radar.api.routes.intents import intent_read
from jobs_radar.domain.enums import LOCAL_OWNER_ID, Visibility
from jobs_radar.schemas.intent_api import ExportedIntent, ExportedProfile, ProfileExport
from jobs_radar.schemas.profile import ProfilePrivacy
from jobs_radar.schemas.profile_api import (
    ProfileCreate,
    ProfileFactsRead,
    ProfileInput,
    ProfileList,
    ProfileRead,
    ProfileRevisionList,
    ProfileRevisionRead,
    ProfileRevisionSummary,
    ProfileSave,
    ProfileSaveResponse,
    RestoreRequest,
)
from jobs_radar.services.intents import IntentService
from jobs_radar.services.profile_data import ProfileDataService
from jobs_radar.services.profiles import ProfileService, ProfileView, RevisionView

router = APIRouter(tags=["profiles"])

Service = Annotated[ProfileService, Depends(get_profile_service)]
Session = Annotated[AsyncSession, Depends(get_session)]


def _facts(view: RevisionView) -> ProfileFactsRead:
    """Attach each skill's canonical name to the stored facts."""
    facts: dict[str, Any] = dict(view.revision.facts_json)
    facts["skills"] = [
        {
            **skill,
            "name": view.skill_names.get(int(skill["skill_id"]), f"Skill {skill['skill_id']}"),
            "kind": view.skill_kinds.get(int(skill["skill_id"]), "technology"),
        }
        for skill in facts["skills"]
    ]
    return ProfileFactsRead.model_validate(facts)


def _summary(view: RevisionView) -> ProfileRevisionSummary:
    revision = view.revision
    return ProfileRevisionSummary(
        profile_revision_id=revision.profile_revision_id,
        revision_number=revision.revision_number,
        created_at=revision.created_at,
        change_summary=revision.change_summary,
    )


def _revision(view: RevisionView) -> ProfileRevisionRead:
    return ProfileRevisionRead(
        **_summary(view).model_dump(),
        facts=_facts(view),
        privacy=ProfilePrivacy.model_validate(view.revision.privacy_json),
    )


def profile_read(view: ProfileView) -> ProfileRead:
    """Map a profile view to its API model."""
    profile = view.profile
    return ProfileRead(
        career_profile_id=profile.career_profile_id,
        title=profile.title,
        visibility=Visibility(profile.visibility),
        version=profile.version,
        current_revision=_revision(view.current) if view.current else None,
    )


@router.post("/profiles", response_model=ProfileRead, status_code=201)
async def create_profile(body: ProfileCreate, service: Service, session: Session) -> ProfileRead:
    """Create a blank named profile."""
    view = await service.create(LOCAL_OWNER_ID, body.title)
    view.profile.visibility = body.visibility.value
    await session.commit()
    return profile_read(view)


@router.get("/profiles", response_model=ProfileList)
async def list_profiles(service: Service) -> ProfileList:
    """List the owner's profiles with their current revisions."""
    return ProfileList(
        items=[profile_read(view) for view in await service.list_profiles(LOCAL_OWNER_ID)]
    )


@router.get("/profiles/{career_profile_id}", response_model=ProfileRead)
async def get_profile(career_profile_id: int, service: Service) -> ProfileRead:
    """Return the current projection and current revision of a profile."""
    return profile_read(await service.get(LOCAL_OWNER_ID, career_profile_id))


@router.put("/profiles/{career_profile_id}", response_model=ProfileSaveResponse)
async def save_profile(
    career_profile_id: int, body: ProfileSave, service: Service, session: Session
) -> ProfileSaveResponse:
    """Save the profile as its next immutable revision (no revision when nothing changed)."""
    result = await service.save(
        LOCAL_OWNER_ID,
        career_profile_id,
        ProfileInput.model_validate(
            body.model_dump(exclude={"expected_current_revision", "change_summary"})
        ),
        expected_current_revision=body.expected_current_revision,
        change_summary=body.change_summary,
    )
    await session.commit()
    return ProfileSaveResponse(
        created=result.created,
        profile=profile_read(await service.get(LOCAL_OWNER_ID, career_profile_id)),
    )


@router.get("/profiles/{career_profile_id}/revisions", response_model=ProfileRevisionList)
async def list_profile_revisions(career_profile_id: int, service: Service) -> ProfileRevisionList:
    """List the immutable revisions of a profile, newest first."""
    views = await service.revisions(LOCAL_OWNER_ID, career_profile_id)
    return ProfileRevisionList(items=[_summary(view) for view in views])


@router.get(
    "/profiles/{career_profile_id}/revisions/{profile_revision_id}",
    response_model=ProfileRevisionRead,
)
async def get_profile_revision(
    career_profile_id: int, profile_revision_id: int, service: Service
) -> ProfileRevisionRead:
    """Return one revision with its facts and provenance."""
    return _revision(await service.revision(LOCAL_OWNER_ID, career_profile_id, profile_revision_id))


@router.post(
    "/profiles/{career_profile_id}/revisions/{profile_revision_id}/restore",
    response_model=ProfileSaveResponse,
)
async def restore_profile_revision(
    career_profile_id: int,
    profile_revision_id: int,
    body: RestoreRequest,
    service: Service,
    session: Session,
) -> ProfileSaveResponse:
    """Make an old revision's content the next revision."""
    result = await service.restore(
        LOCAL_OWNER_ID,
        career_profile_id,
        profile_revision_id,
        expected_current_revision=body.expected_current_revision,
    )
    await session.commit()
    return ProfileSaveResponse(
        created=result.created,
        profile=profile_read(await service.get(LOCAL_OWNER_ID, career_profile_id)),
    )


@router.get("/profiles/{career_profile_id}/export", response_model=ProfileExport)
async def export_profile(
    career_profile_id: int,
    service: Service,
    intents: Annotated[IntentService, Depends(get_intent_service)],
    data: Annotated[ProfileDataService, Depends(get_profile_data_service)],
    session: Session,
    response: Response,
) -> ProfileExport:
    """Portable export: profile, intents, history, document metadata, proposals and inbox state.

    It contains no credentials, provider setup, original CV or CV text.
    """
    view = await service.get(LOCAL_OWNER_ID, career_profile_id)
    current = view.current
    exported = []
    for intent_view in await intents.list_for_profile(LOCAL_OWNER_ID, career_profile_id):
        read = intent_read(intent_view)
        if read.current_revision is not None:
            exported.append(
                ExportedIntent(
                    title=read.title,
                    enabled=read.enabled,
                    definition=read.current_revision.definition,
                )
            )
    history = await data.history(LOCAL_OWNER_ID, career_profile_id)
    await session.commit()  # the audit event of the export
    response.headers["Content-Disposition"] = (
        f'attachment; filename="jobs-radar-profile-{career_profile_id}.json"'
    )
    return ProfileExport(
        **history,
        exported_at=datetime.now(UTC),
        profile=ExportedProfile(
            title=view.profile.title,
            facts=_facts(current) if current else None,
            privacy=ProfilePrivacy.model_validate(current.revision.privacy_json)
            if current
            else None,
        ),
        intents=exported,
    )


@router.delete("/profiles/{career_profile_id}")
async def delete_profile(
    career_profile_id: int,
    confirm: str,
    data: Annotated[ProfileDataService, Depends(get_profile_data_service)],
    session: Session,
) -> dict[str, dict[str, int]]:
    """Delete a profile and its data after the exact title is typed back (audited, UC-08)."""
    counts = await data.delete(LOCAL_OWNER_ID, career_profile_id, confirm=confirm)
    await session.commit()
    return {"deleted": counts}
