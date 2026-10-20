"""Data access for domain packs: which terms they list and which ones the owner switched on."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import OwnerPack, TaxonomyTermPack


class PackRepository:
    """Reads and writes pack memberships and the owner's activations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def memberships(self) -> list[TaxonomyTermPack]:
        """Return every membership row."""
        return list((await self._session.execute(select(TaxonomyTermPack))).scalars())

    async def add_membership(self, term_id: int, pack_key: str, pack_version: int) -> None:
        """Record that ``pack_key`` lists the term."""
        self._session.add(
            TaxonomyTermPack(taxonomy_term_id=term_id, pack_key=pack_key, pack_version=pack_version)
        )
        await self._session.flush()

    async def remove_memberships(self, membership_ids: list[int]) -> None:
        """Forget memberships that a newer pack file no longer lists."""
        if membership_ids:
            await self._session.execute(
                delete(TaxonomyTermPack).where(
                    TaxonomyTermPack.taxonomy_term_pack_id.in_(membership_ids)
                )
            )

    async def active_keys(self, owner_id: int) -> set[str]:
        """Return the keys of the packs the owner switched on."""
        rows = await self._session.execute(
            select(OwnerPack.pack_key).where(OwnerPack.owner_id == owner_id)
        )
        return set(rows.scalars())

    async def activate(self, owner_id: int, pack_key: str) -> None:
        """Switch a pack on for the owner."""
        self._session.add(OwnerPack(owner_id=owner_id, pack_key=pack_key))
        await self._session.flush()

    async def deactivate(self, owner_id: int, pack_key: str) -> None:
        """Switch a pack off for the owner."""
        await self._session.execute(
            delete(OwnerPack).where(OwnerPack.owner_id == owner_id, OwnerPack.pack_key == pack_key)
        )
