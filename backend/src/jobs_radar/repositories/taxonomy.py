"""Data access for the controlled vocabularies."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import TaxonomyTerm


class TaxonomyRepository:
    """Reads taxonomy terms."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def terms(self) -> list[TaxonomyTerm]:
        """Return the current terms (not replaced by a merge), ordered by kind then label."""
        rows = await self._session.execute(
            select(TaxonomyTerm)
            .where(TaxonomyTerm.replaced_by_taxonomy_term_id.is_(None))
            .order_by(TaxonomyTerm.kind, TaxonomyTerm.label)
        )
        return list(rows.scalars())

    async def keys_by_kind(self) -> dict[str, set[str]]:
        """Return the current term keys of each kind."""
        grouped: dict[str, set[str]] = {}
        for term in await self.terms():
            grouped.setdefault(term.kind, set()).add(term.term_key)
        return grouped
