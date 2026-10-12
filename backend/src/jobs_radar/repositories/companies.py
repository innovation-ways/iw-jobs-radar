"""Data access for companies (document 13, section 9)."""

from collections.abc import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import Company, CompanyAlias, CompanyFollow, CompanyIgnore


def normalise_company_name(name: str) -> str:
    """Lower-case the name and collapse whitespace; used for matching and search."""
    return " ".join(name.lower().split())


class CompanyRepository:
    """Reads and creates companies."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, name: str) -> Company:
        """Return the company with this (normalised) name or alias, creating it if needed."""
        normalised = normalise_company_name(name)
        existing = (
            await self._session.execute(
                select(Company).where(Company.name_normalised == normalised).limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        by_alias = (
            await self._session.execute(
                select(Company)
                .join(CompanyAlias, CompanyAlias.company_id == Company.company_id)
                .where(CompanyAlias.alias_normalised == normalised)
                .limit(1)
            )
        ).scalar_one_or_none()
        if by_alias is not None:
            return by_alias
        company = Company(canonical_name=" ".join(name.split()), name_normalised=normalised)
        self._session.add(company)
        await self._session.flush()
        await self._session.refresh(company)
        return company

    async def get_or_create_many(self, names: Iterable[str]) -> dict[str, int]:
        """Return ``{name: company_id}``, creating the missing companies (ADR-063).

        Sources are collected at the same time and ``company.name_normalised`` is not unique, so
        two runs could both create "Acme". A transaction-scoped advisory lock per normalised name
        serialises them: the second sees the first one's company. The locks are taken in sorted
        order, so two callers can never wait on each other. The caller commits promptly, which
        releases the locks.
        """
        names = list(names)
        by_normalised = {normalise_company_name(name): name for name in names}
        found: dict[str, int] = {}
        for normalised in sorted(by_normalised):
            await self._session.execute(
                select(func.pg_advisory_xact_lock(func.hashtext(normalised)))
            )
            name = by_normalised[normalised]
            found[normalised] = (await self.get_or_create(name)).company_id
        # Several spellings can share one normalised name; every spelling maps to its company.
        return {name: found[normalise_company_name(name)] for name in names}


class CompanyFollowRepository:
    """Reads and changes which companies an owner follows (ADR-053)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def follow(self, owner_id: int, company_id: int) -> None:
        """Follow the company; following twice is a no-op."""
        await self._session.execute(
            insert(CompanyFollow)
            .values(owner_id=owner_id, company_id=company_id)
            .on_conflict_do_nothing(constraint="uq_company_follow_owner_id_company_id")
        )

    async def unfollow(self, owner_id: int, company_id: int) -> None:
        """Stop following the company; the row is really deleted (no soft delete)."""
        await self._session.execute(
            delete(CompanyFollow).where(
                CompanyFollow.owner_id == owner_id, CompanyFollow.company_id == company_id
            )
        )


class CompanyIgnoreRepository:
    """Reads and changes which companies an owner ignores (ADR-061)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ignore(self, owner_id: int, company_id: int) -> bool:
        """Ignore the company; returns False when it was already ignored."""
        inserted = await self._session.execute(
            insert(CompanyIgnore)
            .values(owner_id=owner_id, company_id=company_id)
            .on_conflict_do_nothing(constraint="uq_company_ignore_owner_id_company_id")
            .returning(CompanyIgnore.company_ignore_id)
        )
        return inserted.scalar_one_or_none() is not None

    async def unignore(self, owner_id: int, company_id: int) -> bool:
        """Stop ignoring the company (the row is deleted); returns False when it was not ignored."""
        deleted = await self._session.execute(
            delete(CompanyIgnore)
            .where(CompanyIgnore.owner_id == owner_id, CompanyIgnore.company_id == company_id)
            .returning(CompanyIgnore.company_ignore_id)
        )
        return deleted.first() is not None
