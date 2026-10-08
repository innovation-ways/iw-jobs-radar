"""API contracts for the offline location search."""

from jobs_radar.schemas.common import CountryCode, Latitude, Longitude, StrictModel


class PlaceRead(StrictModel):
    """A city the owner can pick as a base place."""

    label: str
    city: str
    country: CountryCode
    latitude: Latitude
    longitude: Longitude
    timezone: str
    population: int


class PlaceList(StrictModel):
    """Search results, most populous first."""

    items: list[PlaceRead]
