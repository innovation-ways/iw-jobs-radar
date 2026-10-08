"""AI & privacy endpoints (document 07, section 6). Credentials are write-only."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_ai_settings_service, get_session
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.ai_settings import (
    AiSettingsRead,
    ConnectionCreate,
    ConnectionRead,
    ConnectionSelect,
    ConnectionTestRead,
    ConnectionUpdate,
    CredentialWrite,
    PrivacyRead,
    PrivacyUpdate,
)
from jobs_radar.services.ai_settings import AiSettingsService, ConnectionView, connection_view

router = APIRouter(tags=["ai-settings"])

Service = Annotated[AiSettingsService, Depends(get_ai_settings_service)]
Session = Annotated[AsyncSession, Depends(get_session)]


def connection_read(view: ConnectionView) -> ConnectionRead:
    """Map a connection view to its API model."""
    return ConnectionRead.model_validate(view, from_attributes=True)


@router.get("/settings/ai", response_model=AiSettingsRead)
async def get_ai_settings(service: Service, session: Session) -> AiSettingsRead:
    """Return the safe projection: connections with credential status, mode and privacy."""
    view = await service.get(LOCAL_OWNER_ID)
    await session.commit()  # first use creates the privacy row
    return AiSettingsRead(
        mode=view.mode,
        import_connection_id=view.import_connection_id,
        jobs_connection_id=view.jobs_connection_id,
        key_configured=view.key_configured,
        connections=[connection_read(c) for c in view.connections],
        privacy=PrivacyRead(
            redact_contact_details=view.privacy.redact_contact_details,
            version=view.privacy.version,
        ),
    )


@router.post(
    "/settings/ai/connections", response_model=ConnectionRead, status_code=status.HTTP_201_CREATED
)
async def create_connection(
    body: ConnectionCreate, service: Service, session: Session
) -> ConnectionRead:
    """Create a connection (no credential, not in use)."""
    created = await service.create_connection(LOCAL_OWNER_ID, **body.model_dump())
    await session.commit()
    return connection_read(connection_view(created))


@router.put("/settings/ai/connections/{provider_connection_id}", response_model=ConnectionRead)
async def update_connection(
    provider_connection_id: int, body: ConnectionUpdate, service: Service, session: Session
) -> ConnectionRead:
    """Change the non-secret metadata of a connection."""
    updated = await service.update_connection(
        LOCAL_OWNER_ID, provider_connection_id, **body.model_dump()
    )
    await session.commit()
    return connection_read(connection_view(updated))


@router.delete(
    "/settings/ai/connections/{provider_connection_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_connection(
    provider_connection_id: int, service: Service, session: Session
) -> Response:
    """Delete a connection and its encrypted credential."""
    await service.delete_connection(LOCAL_OWNER_ID, provider_connection_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/settings/ai/connections/{provider_connection_id}/credential", response_model=ConnectionRead
)
async def write_credential(
    provider_connection_id: int, body: CredentialWrite, service: Service, session: Session
) -> ConnectionRead:
    """Store the credential (write-only: only its status is ever returned)."""
    view = await service.set_credential(LOCAL_OWNER_ID, provider_connection_id, body.secret)
    await session.commit()
    return connection_read(view)


@router.delete(
    "/settings/ai/connections/{provider_connection_id}/credential", response_model=ConnectionRead
)
async def delete_credential(
    provider_connection_id: int, service: Service, session: Session
) -> ConnectionRead:
    """Delete the stored credential."""
    view = await service.clear_credential(LOCAL_OWNER_ID, provider_connection_id)
    await session.commit()
    return connection_read(view)


@router.post(
    "/settings/ai/connections/{provider_connection_id}/test", response_model=ConnectionTestRead
)
async def test_connection(provider_connection_id: int, service: Service) -> ConnectionTestRead:
    """Check the connection and list models; sends only a model-list request."""
    result = await service.test_connection(LOCAL_OWNER_ID, provider_connection_id)
    return ConnectionTestRead.model_validate(result, from_attributes=True)


@router.put("/settings/ai/import-connection", response_model=AiSettingsRead)
async def select_import_connection(
    body: ConnectionSelect, service: Service, session: Session
) -> AiSettingsRead:
    """Choose the connection used to import a CV, or switch it off (No AI)."""
    if body.provider_connection_id is None:
        await service.deactivate_import(LOCAL_OWNER_ID)
    else:
        await service.activate_for_import(LOCAL_OWNER_ID, body.provider_connection_id)
    await session.commit()
    return await get_ai_settings(service, session)


@router.put("/settings/ai/jobs-connection", response_model=AiSettingsRead)
async def select_jobs_connection(
    body: ConnectionSelect, service: Service, session: Session
) -> AiSettingsRead:
    """Choose the local connection that analyses collected jobs, or switch it off."""
    if body.provider_connection_id is None:
        await service.deactivate_jobs(LOCAL_OWNER_ID)
    else:
        await service.activate_for_jobs(LOCAL_OWNER_ID, body.provider_connection_id)
    await session.commit()
    return await get_ai_settings(service, session)


@router.put("/settings/privacy", response_model=PrivacyRead)
async def update_privacy(body: PrivacyUpdate, service: Service, session: Session) -> PrivacyRead:
    """Change the privacy policy for remote calls."""
    setting = await service.update_privacy(
        LOCAL_OWNER_ID,
        redact_contact_details=body.redact_contact_details,
        expected_version=body.expected_version,
    )
    await session.commit()
    return PrivacyRead(
        redact_contact_details=setting.redact_contact_details, version=setting.version
    )
