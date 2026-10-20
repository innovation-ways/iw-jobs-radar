"""API contracts for the pre-filter areas (ADR-080)."""

from jobs_radar.schemas.common import StrictModel


class AreaRead(StrictModel):
    """An area of work a job board can be narrowed to."""

    key: str
    label: str


class AreaList(StrictModel):
    """The areas of the packs the owner switched on, in pack order."""

    areas: list[AreaRead]
