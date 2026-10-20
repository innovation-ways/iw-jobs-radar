"""The pre-filter rules in force for an owner: the areas and noise of the packs switched on.

Areas and noise are read from the shipped pack files (ADR-080, phase 5); the database only says
which packs the owner uses. Nothing is stored per area, so a newer pack improves the filter
without a migration.
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.domain.prefilter import Area, PrefilterRules
from jobs_radar.repositories.packs import PackRepository
from jobs_radar.schemas.pack import PackFile
from jobs_radar.services.packs import shipped_packs


def rules_from_packs(packs: Sequence[PackFile]) -> PrefilterRules:
    """Combine the areas and the noise of the given packs into one set of rules."""
    return PrefilterRules.merged(
        [
            PrefilterRules(
                tuple(Area(a.key, a.label, tuple(a.keywords)) for a in pack.areas),
                tuple(pack.noise),
            )
            for pack in packs
        ]
    )


class PrefilterService:
    """Builds the pre-filter rules of an owner."""

    def __init__(self, session: AsyncSession, packs: Sequence[PackFile] | None = None) -> None:
        self._packs = PackRepository(session)
        self._files = list(shipped_packs() if packs is None else packs)

    async def rules_for_owner(self, owner_id: int) -> PrefilterRules:
        """Return the rules of the packs the owner switched on (empty when none is on)."""
        active = await self._packs.active_keys(owner_id)
        return rules_from_packs([pack for pack in self._files if pack.key in active])
