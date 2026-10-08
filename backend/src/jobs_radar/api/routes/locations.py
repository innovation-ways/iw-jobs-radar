"""Offline location search for the base-place pickers (no network, GeoNames data)."""

from typing import Annotated

from fastapi import APIRouter, Query

from jobs_radar.schemas.location import PlaceList, PlaceRead
from jobs_radar.services.locations import load_gazetteer

router = APIRouter(tags=["locations"])


@router.get("/locations/search", response_model=PlaceList)
async def search_locations(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    country: Annotated[str | None, Query(pattern=r"^[A-Z]{2}$")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> PlaceList:
    """Find cities by name prefix, optionally within one country (ISO 3166-1 alpha-2)."""
    places = load_gazetteer().search(q, country=country, limit=limit)
    return PlaceList(items=[PlaceRead(**place.__dict__) for place in places])
