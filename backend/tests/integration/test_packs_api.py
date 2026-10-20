"""The packs endpoints (ADR-080, phase 4). Requests run in the test's transaction."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.services.packs import PackService

pytestmark = pytest.mark.integration


async def test_the_list_shows_every_pack_and_which_ones_are_on(
    isolated_client: httpx.AsyncClient,
) -> None:
    response = await isolated_client.get("/api/v1/packs")
    assert response.status_code == 200
    packs = {p["key"]: p for p in response.json()["packs"]}
    assert len(packs) == 10
    software = packs["software_data_it"]
    assert software["active"] is True  # the test installation models the owner's
    assert (software["role_family_count"], software["sector_count"]) == (25, 16)
    assert packs["construction_trades"]["active"] is False
    assert response.json()["active_count"] == 1
    assert software["name"] and software["description"] and software["version"] == 1


async def test_a_pack_is_switched_on_and_its_terms_reach_the_forms(
    isolated_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    # The terms of a pack exist once the application has started (the loader ran).
    await PackService(db_session).load()
    before = await _role_family_keys(isolated_client)
    assert "electrician" not in before
    on = await isolated_client.put("/api/v1/packs/construction_trades", json={"active": True})
    assert on.status_code == 200 and on.json()["active"] is True
    assert "electrician" in await _role_family_keys(isolated_client)
    off = await isolated_client.put("/api/v1/packs/construction_trades", json={"active": False})
    assert off.json()["active"] is False
    assert "electrician" not in await _role_family_keys(isolated_client)


async def test_an_unknown_pack_is_not_found(isolated_client: httpx.AsyncClient) -> None:
    response = await isolated_client.put("/api/v1/packs/no_such_pack", json={"active": True})
    assert response.status_code == 404


async def test_a_pack_cannot_be_deleted(isolated_client: httpx.AsyncClient) -> None:
    assert (await isolated_client.delete("/api/v1/packs/construction_trades")).status_code == 405


async def _role_family_keys(client: httpx.AsyncClient) -> set[str]:
    groups = (await client.get("/api/v1/taxonomy")).json()["groups"]
    return {t["term_key"] for g in groups if g["kind"] == "role_family" for t in g["terms"]}
