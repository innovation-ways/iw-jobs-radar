"""API contracts for domain packs (ADR-080)."""

from jobs_radar.schemas.common import StrictModel


class PackRead(StrictModel):
    """A domain pack as the owner sees it."""

    key: str
    name: str
    description: str
    version: int
    role_family_count: int
    sector_count: int
    active: bool


class PackList(StrictModel):
    """Every shipped pack; ``active_count`` is how many the owner switched on."""

    packs: list[PackRead]
    active_count: int


class PackActivation(StrictModel):
    """Switch a pack on or off."""

    active: bool
