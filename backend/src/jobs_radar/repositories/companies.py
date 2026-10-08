"""Data access for companies (document 13, section 9)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import Company, CompanyAlias


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
