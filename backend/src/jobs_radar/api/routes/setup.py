"""First-run setup endpoints (ADR-080, phase 6c)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_session
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.setup_api import IntentDefaultsRead, SetupStatusRead
from jobs_radar.services.setup import SetupService

router = APIRouter(prefix="/setup", tags=["setup"])


def _service(session: Annotated[AsyncSession, Depends(get_session)]) -> SetupService:
    return SetupService(session)


Service = Annotated[SetupService, Depends(_service)]


@router.get("/status", response_model=SetupStatusRead)
async def setup_status(service: Service) -> SetupStatusRead:
    """Say whether the installation still has to be set up (no profile and no pack on)."""
    status = await service.status(LOCAL_OWNER_ID)
    return SetupStatusRead(
        needs_setup=status.needs_setup,
        has_profile=status.has_profile,
        active_pack_count=status.active_pack_count,
    )


@router.get("/intent-defaults", response_model=IntentDefaultsRead)
async def intent_defaults(service: Service) -> IntentDefaultsRead:
    """Return what a first search intent starts with, from the first pack switched on."""
    defaults = await service.intent_defaults(LOCAL_OWNER_ID)
    return IntentDefaultsRead(
        pack_key=defaults.pack_key,
        work_arrangements=defaults.work_arrangements,
        schedules=defaults.schedules,
        travel_levels=defaults.travel_levels,
        weights=defaults.weights,
        reject_missing_credentials=defaults.reject_missing_credentials,
    )
