"""Following and unfollowing a company (ADR-053)."""

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.factories import make_company

from jobs_radar.db.models import CompanyFollow

pytestmark = pytest.mark.integration

BASE = "/api/v1"


async def new_company(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        company = await make_company(session, "Follow API Co")
        await session.commit()
        return company.company_id


async def follow_rows(session_factory: async_sessionmaker[AsyncSession], company_id: int) -> int:
    async with session_factory() as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(CompanyFollow)
                .where(CompanyFollow.company_id == company_id)
            )
        ).scalar_one()


async def test_follow_is_idempotent_and_unfollow_deletes_the_row(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    company_id = await new_company(session_factory)
    url = f"{BASE}/companies/{company_id}/follow"

    for _ in range(2):  # the second call changes nothing
        response = await client.put(url)
        assert response.status_code == 200, response.text
        assert response.json() == {"company_id": company_id, "is_followed": True}
    assert await follow_rows(session_factory, company_id) == 1

    for _ in range(2):
        response = await client.delete(url)
        assert response.status_code == 200, response.text
        assert response.json() == {"company_id": company_id, "is_followed": False}
    assert await follow_rows(session_factory, company_id) == 0


async def test_an_unknown_company_is_404(client: httpx.AsyncClient) -> None:
    for call in (client.put, client.delete):
        response = await call(f"{BASE}/companies/999999999/follow")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
