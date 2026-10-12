"""Finding or creating many companies at once, safe against runs that overlap (ADR-063)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import unique

from jobs_radar.db.models import Company
from jobs_radar.repositories.companies import CompanyRepository

pytestmark = pytest.mark.integration


async def test_names_that_normalise_alike_share_one_company(db_session: AsyncSession) -> None:
    name = unique("Acme Robotics")
    found = await CompanyRepository(db_session).get_or_create_many([name, name.upper(), name])
    assert len({found[item] for item in found}) == 1
    count = (
        await db_session.execute(
            select(func.count()).select_from(Company).where(Company.canonical_name.ilike(name))
        )
    ).scalar_one()
    assert count == 1


async def test_an_existing_company_is_reused_and_new_ones_are_created(
    db_session: AsyncSession,
) -> None:
    repository = CompanyRepository(db_session)
    known = (await repository.get_or_create(unique("Known Co"))).company_id
    fresh = unique("Fresh Co")
    found = await repository.get_or_create_many([fresh, "known co-never"])
    again = await repository.get_or_create_many([fresh])
    assert again[fresh] == found[fresh] != known
    assert (await repository.get_or_create_many([])) == {}
