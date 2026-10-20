"""The areas of work the owner can narrow job boards to (ADR-080)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from jobs_radar.api.deps import get_prefilter_service
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.prefilter_api import AreaList, AreaRead
from jobs_radar.services.prefilter import PrefilterService

router = APIRouter(prefix="/prefilter", tags=["prefilter"])

Service = Annotated[PrefilterService, Depends(get_prefilter_service)]


@router.get("/areas", response_model=AreaList)
async def list_areas(service: Service) -> AreaList:
    """List the areas of work offered by the packs the owner switched on."""
    rules = await service.rules_for_owner(LOCAL_OWNER_ID)
    return AreaList(areas=[AreaRead(key=a.key, label=a.label) for a in rules.areas])
