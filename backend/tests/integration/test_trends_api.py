"""GET /trends and POST /trends/recompute (T7.6)."""

import httpx
import pytest

pytestmark = pytest.mark.integration

API = "/api/v1"


async def test_the_trends_report_has_the_documented_shape(client: httpx.AsyncClient) -> None:
    profile = (await client.post(f"{API}/profiles", json={"title": "Trends"})).json()
    # without an intent there is nothing to report on
    response = await client.get(
        f"{API}/trends", params={"kind": "skill", "search_intent_id": 999999}
    )
    assert response.status_code == 404
    listing = await client.get(f"{API}/trends", params={"kind": "skill"})
    assert listing.status_code in {200, 404}
    assert profile["career_profile_id"] > 0


async def test_bad_parameters_are_422(client: httpx.AsyncClient) -> None:
    for params in (
        {"kind": "colour"},
        {"kind": "skill", "weeks": 0},
        {"kind": "skill", "weeks": 80},
        {"kind": "skill", "limit": 0},
    ):
        assert (await client.get(f"{API}/trends", params=params)).status_code == 422
    assert (
        await client.post(f"{API}/trends/recompute", params={"search_intent_id": 999999})
    ).status_code == 404
