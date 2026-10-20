"""Data access for the controlled vocabularies."""

from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import OwnerPack, TaxonomyTerm, TaxonomyTermPack, TaxonomyVersion
from jobs_radar.domain.enums import LOCAL_OWNER_ID

_MAX_CHAIN = 10  # a merge chain is never this long; the limit only guards against a data error


def in_scope_of_packs(owner_id: int) -> ColumnElement[bool]:
    """Match the terms that no pack lists, or that a pack the owner switched on lists."""
    lists_term = TaxonomyTermPack.taxonomy_term_id == TaxonomyTerm.taxonomy_term_id
    in_no_pack = ~exists().where(lists_term)
    in_an_active_pack = exists().where(
        lists_term,
        TaxonomyTermPack.pack_key == OwnerPack.pack_key,
        OwnerPack.owner_id == owner_id,
    )
    return or_(in_no_pack, in_an_active_pack)


class TaxonomyRepository:
    """Reads taxonomy terms for one owner (V1 has a single local owner)."""

    def __init__(self, session: AsyncSession, owner_id: int = LOCAL_OWNER_ID) -> None:
        self._session = session
        self._owner_id = owner_id

    async def terms(
        self, *, include_inactive: bool = False, all_packs: bool = False
    ) -> list[TaxonomyTerm]:
        """Return the current terms (not replaced by a merge), ordered by kind then label.

        By default these are the terms *offered* to the owner: switched on, and either in no pack
        or in a pack the owner switched on (ADR-080). ``include_inactive`` adds the terms the owner
        switched off; ``all_packs`` also adds the terms of packs that are not switched on, which is
        what checking a stored intent needs.
        """
        query = (
            select(TaxonomyTerm)
            .where(TaxonomyTerm.replaced_by_taxonomy_term_id.is_(None))
            .order_by(TaxonomyTerm.kind, TaxonomyTerm.label)
        )
        if not include_inactive:
            query = query.where(TaxonomyTerm.is_active.is_(True))
        if not all_packs:
            query = query.where(in_scope_of_packs(self._owner_id))
        return list((await self._session.execute(query)).scalars())

    async def keys_by_kind(
        self, *, include_inactive: bool = False, all_packs: bool = False
    ) -> dict[str, set[str]]:
        """Return the current term keys of each kind (see :meth:`terms` for the flags).

        The extraction asks the model with offered terms only; checking a stored intent needs every
        term, including the ones switched off or left behind in a pack after the intent was saved.
        """
        grouped: dict[str, set[str]] = {}
        for term in await self.terms(include_inactive=include_inactive, all_packs=all_packs):
            grouped.setdefault(term.kind, set()).add(term.term_key)
        return grouped

    async def find(self, kind: str, term_key: str) -> TaxonomyTerm | None:
        """Return the term with this key, active or not (``None`` if there is none)."""
        return await self._session.scalar(
            select(TaxonomyTerm).where(TaxonomyTerm.kind == kind, TaxonomyTerm.term_key == term_key)
        )

    async def get(self, taxonomy_term_id: int) -> TaxonomyTerm | None:
        """Return the term with this id (``None`` if there is none)."""
        return await self._session.get(TaxonomyTerm, taxonomy_term_id)

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
        """Return the offered term keys of each kind in the order the terms were created."""
        rows = await self._session.execute(
            select(TaxonomyTerm.kind, TaxonomyTerm.term_key)
            .where(TaxonomyTerm.replaced_by_taxonomy_term_id.is_(None))
            .where(TaxonomyTerm.is_active.is_(True))
            .where(in_scope_of_packs(self._owner_id))
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

    async def replacements(self) -> dict[str, dict[str, str]]:
        """Map each merged term key to the key of the term that replaced it, by kind.

        A chain (A merged into B, B into C) is followed to its end, so every key points at a term
        that is still current.
        """
        rows = (await self._session.execute(select(TaxonomyTerm))).scalars().all()
        by_id = {term.taxonomy_term_id: term for term in rows}
        result: dict[str, dict[str, str]] = {}
        for term in rows:
            current, hops = term, 0
            while current.replaced_by_taxonomy_term_id is not None and hops < _MAX_CHAIN:
                current = by_id[current.replaced_by_taxonomy_term_id]
                hops += 1
            if current is not term:
                result.setdefault(term.kind, {})[term.term_key] = current.term_key
        return result
