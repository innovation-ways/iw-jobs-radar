"""Company dossier API and the GitHub token endpoints (T7.2, T7.3)."""

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.factories import make_company

from jobs_radar.adapters.enrichment.base import EntityCandidate, FactValue
from jobs_radar.db.models import IntegrationCredential
from jobs_radar.services.enrichment import EnrichmentAdapters

pytestmark = pytest.mark.integration

BASE = "/api/v1"
TOKEN = "ghp_api_token_must_not_leak"


class Wikidata:
    async def find(self, name: str) -> list[EntityCandidate]:
        fact = FactValue(
            "software industry", "wikidata", "https://www.wikidata.org/wiki/Q7", "CC0-1.0"
        )
        return [
            EntityCandidate(
                "wikidata",
                "Q7",
                name,
                "software company",
                "https://elsewhere.example",
                {
                    "industry": fact,
                    "homepage": FactValue(
                        "https://elsewhere.example",
                        "wikidata",
                        "https://www.wikidata.org/wiki/Q7",
                        "CC0-1.0",
                    ),
                },
            ),
        ]


@pytest_asyncio.fixture(autouse=True)
async def adapters(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, session_factory: async_sessionmaker[AsyncSession]
) -> AsyncIterator[None]:
    monkeypatch.setattr(
        app.state, "enrichment_adapters", EnrichmentAdapters(wikidata=Wikidata()), raising=False
    )
    yield
    async with session_factory() as session:
        await session.execute(delete(IntegrationCredential))
        await session.commit()


async def new_company(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        company = await make_company(session, "Dossier API Co")
        await session.commit()
        return company.company_id


async def test_dossier_enrich_and_the_owner_decides(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    company_id = await new_company(session_factory)
    dossier = (await client.get(f"{BASE}/companies/{company_id}")).json()
    assert dossier["name"] == "Dossier API Co" and dossier["stale"] is True
    assert dossier["facts"] == [] and dossier["candidates"] == [] and len(dossier["hiring"]) == 12

    enriched = (await client.post(f"{BASE}/companies/{company_id}/enrich")).json()
    assert enriched["stale"] is False and enriched["facts"] == []  # unmatched: nothing stored yet
    candidate = enriched["candidates"][0]
    assert candidate["website"] == "https://elsewhere.example"

    confirmed = await client.post(
        f"{BASE}/companies/{company_id}/candidates/{candidate['company_enrichment_candidate_id']}/confirm"
    )
    assert confirmed.status_code == 200
    body = confirmed.json()
    fact = next(f for f in body["facts"] if f["fact_key"] == "industry")
    assert (fact["value"], fact["label"], fact["source_name"], fact["licence"]) == (
        "software industry",
        "Source",
        "wikidata",
        "CC0-1.0",
    )
    assert body["homepage_url"] == "https://elsewhere.example" and body["candidates"] == []

    again = await client.post(
        f"{BASE}/companies/{company_id}/candidates/{candidate['company_enrichment_candidate_id']}/reject"
    )
    assert again.status_code == 409


async def test_unknown_companies_and_candidates_are_404(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    company_id = await new_company(session_factory)
    assert (await client.get(f"{BASE}/companies/999999")).status_code == 404
    assert (await client.post(f"{BASE}/companies/999999/enrich")).status_code == 404
    assert (
        await client.post(f"{BASE}/companies/{company_id}/candidates/999999/confirm")
    ).status_code == 404


async def test_the_github_token_is_write_only(client: httpx.AsyncClient) -> None:
    before = (await client.get(f"{BASE}/settings/ai")).json()
    assert before["integrations"] == {"github": "none"}
    saved = await client.put(
        f"{BASE}/settings/integrations/github/credential", json={"secret": TOKEN}
    )
    assert (
        saved.status_code == 200 and saved.json() == {"github": "saved"} and TOKEN not in saved.text
    )
    shown = (await client.get(f"{BASE}/settings/ai")).text
    assert TOKEN not in shown and '"github":"saved"' in shown.replace(" ", "")
    cleared = await client.delete(f"{BASE}/settings/integrations/github/credential")
    assert cleared.json() == {"github": "none"}
    assert (
        await client.put(f"{BASE}/settings/integrations/twitter/credential", json={"secret": TOKEN})
    ).status_code == 422
