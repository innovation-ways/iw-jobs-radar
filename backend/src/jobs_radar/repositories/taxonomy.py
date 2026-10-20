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

    async def keys_in_order(self) -> dict[str, list[str]]:
        """Return the current term keys of each kind in the order the terms were created."""
        rows = await self._session.execute(
            select(TaxonomyTerm.kind, TaxonomyTerm.term_key)
            .where(TaxonomyTerm.replaced_by_taxonomy_term_id.is_(None))
            .order_by(TaxonomyTerm.taxonomy_term_id)
        )
        grouped: dict[str, list[str]] = {}
        for kind, key in rows:
            grouped.setdefault(kind, []).append(key)
        return grouped

    async def optional_keys_by_kind(self) -> dict[str, frozenset[str]]:
        """Return the current terms introduced after taxonomy version 1, by kind.

        An intent saved before such a term existed does not list it. The term is therefore optional
        in the closed groups and counts as acceptable (what the form shows for it) until the owner
        chooses a stance (ADR-073).
        """
        rows = await self._session.execute(
            select(TaxonomyTerm.kind, TaxonomyTerm.term_key)
            .where(TaxonomyTerm.replaced_by_taxonomy_term_id.is_(None))
            .where(TaxonomyTerm.introduced_in_taxonomy_version_id > 1)
        )
        grouped: dict[str, set[str]] = {}
        for kind, key in rows:
            grouped.setdefault(kind, set()).add(key)
        return {kind: frozenset(keys) for kind, keys in grouped.items()}
