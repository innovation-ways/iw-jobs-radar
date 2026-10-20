"""Endpoints for domain packs: list them and switch them on or off (ADR-080)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_pack_service, get_session
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.pack_api import PackActivation, PackList, PackRead
from jobs_radar.services.packs import PackInfo, PackService

router = APIRouter(prefix="/packs", tags=["packs"])

Service = Annotated[PackService, Depends(get_pack_service)]
Session = Annotated[AsyncSession, Depends(get_session)]


def _read(info: PackInfo) -> PackRead:
    return PackRead(
        key=info.key,
        name=info.name,
        description=info.description,
        version=info.version,
        role_family_count=info.role_family_count,
        sector_count=info.sector_count,
        active=info.active,
    )


@router.get("", response_model=PackList)
async def list_packs(service: Service) -> PackList:
    """List the packs that ship with the application and which ones are switched on."""
    packs = [_read(info) for info in await service.available(LOCAL_OWNER_ID)]
    return PackList(packs=packs, active_count=sum(1 for pack in packs if pack.active))


@router.put("/{pack_key}", response_model=PackRead)
async def set_pack_active(
    pack_key: str, body: PackActivation, service: Service, session: Session
) -> PackRead:
    """Switch a pack on or off; a repeated request changes nothing. No terms are deleted."""
    await service.set_active(LOCAL_OWNER_ID, pack_key, active=body.active)
    await session.commit()
    info = next(i for i in await service.available(LOCAL_OWNER_ID) if i.key == pack_key)
    return _read(info)
