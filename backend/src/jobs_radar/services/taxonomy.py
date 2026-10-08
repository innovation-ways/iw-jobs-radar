"""Read access to the controlled vocabularies for the interface."""

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import TaxonomyTerm
from jobs_radar.repositories.taxonomy import TaxonomyRepository


class TaxonomyService:
    """Lists the current taxonomy terms grouped by kind."""

    def __init__(self, session: AsyncSession) -> None:
        self._taxonomy = TaxonomyRepository(session)

    async def groups(self) -> dict[str, list[TaxonomyTerm]]:
        """Return the current terms of each kind, ordered by label."""
        grouped: dict[str, list[TaxonomyTerm]] = {}
        for term in await self._taxonomy.terms():
            grouped.setdefault(term.kind, []).append(term)
        return grouped
