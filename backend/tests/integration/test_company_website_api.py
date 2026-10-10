"""Setting a company's website and asking for the deep analysis over HTTP (ADR-054)."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.factories import make_company

pytestmark = pytest.mark.integration

BASE = "/api/v1"


async def new_company(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        company = await make_company(session, "Website API Co")
        await session.commit()
        return company.company_id


async def test_the_owner_sets_the_website_and_it_is_normalised(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    company_id = await new_company(session_factory)
    response = await client.put(
        f"{BASE}/companies/{company_id}/website", json={"url": "www.Northwind.example/about?x=1"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["homepage_url"] == "https://www.northwind.example/"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "ftp://northwind.example",
        "https://boards.greenhouse.io/x",
        "http://10.0.0.1",
    ],
)
async def test_an_unusable_website_is_a_422(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], url: str
) -> None:
    company_id = await new_company(session_factory)
    response = await client.put(f"{BASE}/companies/{company_id}/website", json={"url": url})
    assert response.status_code == 422, response.text


async def test_the_website_of_an_unknown_company_is_a_404(client: httpx.AsyncClient) -> None:
    response = await client.put(
        f"{BASE}/companies/999999/website", json={"url": "https://northwind.example"}
    )
    assert response.status_code == 404


async def test_analysing_without_a_website_is_a_422_and_unknown_is_a_404(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    company_id = await new_company(session_factory)
    response = await client.post(f"{BASE}/companies/{company_id}/analyse")
    assert response.status_code == 422, response.text
    assert "website" in response.json()["error"]["message"]
    assert (await client.post(f"{BASE}/companies/999999/analyse")).status_code == 404
