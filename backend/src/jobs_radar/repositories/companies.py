"""Data access for companies (document 13, section 9)."""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import Company, CompanyAlias, CompanyFollow


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
