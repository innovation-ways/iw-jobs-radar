"""Domain packs: load the shipped files into the vocabulary and let the owner switch them on.

A pack file lists role families and sectors (ADR-080). Loading is safe to repeat and safe after an
upgrade: it only adds terms and memberships, never rewrites a label (so an owner's edit survives a
newer pack), and a term that a loaded pack stops listing is switched off, never deleted.
"""

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from importlib import resources

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import TaxonomyTermPack
from jobs_radar.domain.enums import TermOrigin
from jobs_radar.repositories.packs import PackRepository
from jobs_radar.repositories.taxonomy import TaxonomyRepository
from jobs_radar.schemas.pack import PackFile

_LOCK_KEY = 80_001  # arbitrary application-wide key of the advisory lock that guards loading


def shipped_packs() -> list[PackFile]:
    """Return every pack file that ships inside the package, in file-name order (read once)."""
    return list(_read_shipped_packs())


@cache
def _read_shipped_packs() -> tuple[PackFile, ...]:
    """Read and validate the pack files. They are fixed for the life of the process."""
    packs: list[PackFile] = []
    for entry in sorted(resources.files("jobs_radar.packs").iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".json"):
            try:
                packs.append(PackFile.model_validate(json.loads(entry.read_text("utf-8"))))
            except ValueError as error:
                msg = f"The pack file {entry.name} is not valid: {error}"
                raise ValueError(msg) from error
    return tuple(packs)


@dataclass(frozen=True)
class LoadResult:
    """What a load changed; all zeros means the vocabulary already matched the files."""

    terms_added: int
    memberships_added: int
    terms_retired: int


@dataclass(frozen=True)
class PackInfo:
    """A pack as the owner sees it."""

    key: str
    name: str
    description: str
    version: int
    role_family_count: int
    sector_count: int
    active: bool


class PackService:
    """Loads packs into the vocabulary and records which ones the owner uses. Caller commits."""

    def __init__(self, session: AsyncSession, packs: Sequence[PackFile] | None = None) -> None:
        self._session = session
        self._taxonomy = TaxonomyRepository(session)
        self._packs = PackRepository(session)
        self._files = list(shipped_packs() if packs is None else packs)

    async def load(self) -> LoadResult:
        """Bring the vocabulary in line with the pack files (idempotent)."""
        # Two processes starting together must not load at the same time; the lock is released at
        # the end of the transaction.
        await self._session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK_KEY})
        version_id: int | None = None
        terms_added = memberships_added = terms_retired = 0
        existing = {(m.taxonomy_term_id, m.pack_key): m for m in await self._packs.memberships()}

        async def new_version() -> int:
            nonlocal version_id
            if version_id is None:
                version_id = await self._taxonomy.new_version("domain packs loaded")
            return version_id

        listed: set[tuple[int, str]] = set()
        for pack in self._files:
            for kind, terms in (("role_family", pack.role_families), ("sector", pack.sectors)):
                for item in terms:
                    term = await self._taxonomy.find(kind, item.key)
                    if term is None:
                        term = await self._taxonomy.add(
                            kind=kind,
                            term_key=item.key,
                            label=item.label,
                            origin=TermOrigin.SEED.value,
                            version_id=await new_version(),
                        )
                        terms_added += 1
                    listed.add((term.taxonomy_term_id, pack.key))
                    if (term.taxonomy_term_id, pack.key) not in existing:
                        await self._packs.add_membership(
                            term.taxonomy_term_id, pack.key, pack.version
                        )
                        memberships_added += 1

        terms_retired = await self._retire_unlisted(existing, listed, new_version)
        return LoadResult(terms_added, memberships_added, terms_retired)

    async def _retire_unlisted(
        self,
        existing: Mapping[tuple[int, str], TaxonomyTermPack],
        listed: set[tuple[int, str]],
        new_version: Callable[[], Awaitable[int]],
    ) -> int:
        """Switch off terms that every loaded pack listing them has stopped listing.

        Only packs whose file is loaded can say a term is gone: a membership of a pack that is not
        among the files (an older image, a pack removed on purpose) is left alone.
        """
        loaded = {pack.key for pack in self._files}
        by_term: dict[int, list[tuple[int, str]]] = {}
        for term_id, pack_key in existing:
            by_term.setdefault(term_id, []).append((term_id, pack_key))
        stale_ids: list[int] = []
        retired = 0
        for term_id, rows in by_term.items():
            stale = [row for row in rows if row[1] in loaded and row not in listed]
            stale_ids += [existing[row].taxonomy_term_pack_id for row in stale]
            if len(stale) == len(rows):
                term = await self._taxonomy.get(term_id)
                if term is not None and term.origin == TermOrigin.SEED.value and term.is_active:
                    term.is_active = False
                    await new_version()
                    retired += 1
        await self._packs.remove_memberships(stale_ids)
        return retired

    async def available(self, owner_id: int) -> list[PackInfo]:
        """List the shipped packs with whether the owner switched each one on."""
        active = await self._packs.active_keys(owner_id)
        return [
            PackInfo(
                key=pack.key,
                name=pack.name,
                description=pack.description,
                version=pack.version,
                role_family_count=len(pack.role_families),
                sector_count=len(pack.sectors),
                active=pack.key in active,
            )
            for pack in self._files
        ]

    async def set_active(self, owner_id: int, pack_key: str, *, active: bool) -> None:
        """Switch a pack on or off for the owner; doing what is already the case records nothing."""
        pack = next((p for p in self._files if p.key == pack_key), None)
        if pack is None:
            msg = f"There is no pack '{pack_key}'."
            raise NotFoundError(msg)
        is_on = pack_key in await self._packs.active_keys(owner_id)
        if active == is_on:
            return
        if active:
            await self._packs.activate(owner_id, pack_key)
        else:
            await self._packs.deactivate(owner_id, pack_key)
        state = "switched on" if active else "switched off"
        await self._taxonomy.new_version(f"pack '{pack_key}' {state}")
