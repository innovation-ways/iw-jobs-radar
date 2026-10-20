"""Data access for the controlled vocabularies."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import TaxonomyTerm, TaxonomyVersion


class TaxonomyRepository:
    """Reads taxonomy terms."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def terms(self, *, include_inactive: bool = False) -> list[TaxonomyTerm]:
        """Return the current terms (not replaced by a merge), ordered by kind then label.

        Terms the owner switched off are left out unless ``include_inactive`` is set.
        """
        query = (
            select(TaxonomyTerm)
            .where(TaxonomyTerm.replaced_by_taxonomy_term_id.is_(None))
            .order_by(TaxonomyTerm.kind, TaxonomyTerm.label)
        )
        if not include_inactive:
            query = query.where(TaxonomyTerm.is_active.is_(True))
        return list((await self._session.execute(query)).scalars())

    async def keys_by_kind(self, *, include_inactive: bool = False) -> dict[str, set[str]]:
        """Return the current term keys of each kind.

        The extraction asks the model with active terms only; checking a stored intent needs every
        term, including the ones switched off after the intent was saved.
        """
        grouped: dict[str, set[str]] = {}
        for term in await self.terms(include_inactive=include_inactive):
            grouped.setdefault(term.kind, set()).add(term.term_key)
        return grouped

    async def find(self, kind: str, term_key: str) -> TaxonomyTerm | None:
        """Return the term with this key, active or not (``None`` if there is none)."""
        return await self._session.scalar(
            select(TaxonomyTerm).where(TaxonomyTerm.kind == kind, TaxonomyTerm.term_key == term_key)
        )

    async def labels_of_kind(self, kind: str) -> list[str]:
        """Return the labels of every term of ``kind`` (active or not), for duplicate checks."""
        rows = await self._session.execute(
            select(TaxonomyTerm.label).where(TaxonomyTerm.kind == kind)
        )
        return list(rows.scalars())

    async def current_version_id(self) -> int:
        """Return the current taxonomy version (the highest recorded one)."""
        return int(
            (
                await self._session.execute(select(func.max(TaxonomyVersion.taxonomy_version_id)))
            ).scalar_one()
        )

    async def new_version(self, description: str) -> int:
        """Record a taxonomy change and return the new, now current, version number."""
        version = TaxonomyVersion(description=description)
        self._session.add(version)
        await self._session.flush()
        return int(version.taxonomy_version_id)

    async def add(
        self, *, kind: str, term_key: str, label: str, origin: str, version_id: int
    ) -> TaxonomyTerm:
        """Insert a term introduced in ``version_id``."""
        term = TaxonomyTerm(
            kind=kind,
            term_key=term_key,
            label=label,
            origin=origin,
            introduced_in_taxonomy_version_id=version_id,
        )
        self._session.add(term)
        await self._session.flush()
        return term

    async def keys_in_order(self) -> dict[str, list[str]]:
        """Return the active term keys of each kind in the order the terms were created."""
        rows = await self._session.execute(
            select(TaxonomyTerm.kind, TaxonomyTerm.term_key)
            .where(TaxonomyTerm.replaced_by_taxonomy_term_id.is_(None))
            .where(TaxonomyTerm.is_active.is_(True))
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
