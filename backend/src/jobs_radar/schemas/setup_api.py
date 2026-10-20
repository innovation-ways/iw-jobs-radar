"""API contracts for the first-run setup (ADR-080, phase 6c)."""

from jobs_radar.schemas.common import StrictModel


class SetupStatusRead(StrictModel):
    """Whether the installation still has to be set up."""

    needs_setup: bool
    has_profile: bool
    active_pack_count: int


class IntentDefaultsRead(StrictModel):
    """What a first search intent starts with: the first switched-on pack's suggestions."""

    pack_key: str | None
    work_arrangements: dict[str, str]
    schedules: dict[str, str]
    travel_levels: dict[str, str]
    weights: dict[str, int]
    reject_missing_credentials: bool
