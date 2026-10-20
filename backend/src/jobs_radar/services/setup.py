"""First-run setup: whether a new installation still has to be set up, and what to start from.

An installation needs setup when it has neither a profile nor a pack switched on. The suggestions
for a first search intent come from the first pack the owner switched on, their main field (ADR-080,
phase 6c); the other packs add vocabulary only.
"""

from dataclasses import dataclass, field
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.repositories.packs import PackRepository
from jobs_radar.repositories.revisions import ProfileRepository
from jobs_radar.schemas.intent import Weights
from jobs_radar.services.packs import shipped_packs


@dataclass(frozen=True)
class SetupStatus:
    """Whether the owner still has to go through the setup."""

    needs_setup: bool
    has_profile: bool
    active_pack_count: int


@dataclass(frozen=True)
class IntentDefaults:
    """What a first search intent starts with."""

    pack_key: str | None
    work_arrangements: dict[str, str] = field(default_factory=dict)
    schedules: dict[str, str] = field(default_factory=dict)
    travel_levels: dict[str, str] = field(default_factory=dict)
    weights: dict[str, int] = field(default_factory=dict)
    reject_missing_credentials: bool = False


class SetupService:
    """Answers the setup assistant's two questions."""

    def __init__(self, session: AsyncSession) -> None:
        self._packs = PackRepository(session)
        self._profiles = ProfileRepository(session)

    async def status(self, owner_id: int) -> SetupStatus:
        """Say whether the owner has a profile and packs; neither means setup is needed."""
        has_profile = bool(await self._profiles.list_for_owner(owner_id))
        active = len(await self._packs.active_keys(owner_id))
        return SetupStatus(not has_profile and active == 0, has_profile, active)

    async def intent_defaults(self, owner_id: int) -> IntentDefaults:
        """Return the suggestions of the first pack switched on, over the usual weights."""
        usual = cast("dict[str, int]", Weights().model_dump())
        by_key = {pack.key: pack for pack in shipped_packs()}
        for key in await self._packs.active_in_order(owner_id):
            pack = by_key.get(key)
            if pack is None:
                continue
            suggested = pack.defaults
            if suggested is None:
                return IntentDefaults(key, weights=usual)
            return IntentDefaults(
                pack_key=key,
                work_arrangements={k: v.value for k, v in suggested.work_arrangements.items()},
                schedules={k: v.value for k, v in suggested.schedules.items()},
                travel_levels={k: v.value for k, v in suggested.travel_levels.items()},
                weights={**usual, **suggested.weights},
                reject_missing_credentials=suggested.reject_missing_credentials,
            )
        return IntentDefaults(None, weights=usual)
