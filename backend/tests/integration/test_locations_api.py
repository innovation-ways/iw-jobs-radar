"""Location search endpoint used by the base-place pickers (T3.5)."""

import httpx
import pytest

pytestmark = pytest.mark.integration


async def test_search_returns_ranked_places_with_coordinates(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/locations/search", params={"q": "lisb"})
    assert response.status_code == 200
    first = response.json()["items"][0]
    assert first["label"] == "Lisbon, Portugal"
    assert (first["country"], first["timezone"]) == ("PT", "Europe/Lisbon")
    assert first["latitude"] == pytest.approx(38.725, abs=0.01)


async def test_search_can_be_limited_to_a_country(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/v1/locations/search", params={"q": "oei", "country": "PT", "limit": 3}
    )
    items = response.json()["items"]
    assert items and len(items) <= 3 and {i["country"] for i in items} == {"PT"}


@pytest.mark.parametrize(
    "params",
    [
        {"q": ""},
        {"q": "x" * 101},
        {"q": "li", "limit": 0},
        {"q": "li", "limit": 51},
        {"q": "li", "country": "Portugal"},
    ],
)
async def test_invalid_search_input_is_rejected(
    client: httpx.AsyncClient, params: dict[str, object]
) -> None:
    assert (await client.get("/api/v1/locations/search", params=params)).status_code == 422


async def test_no_match_returns_an_empty_list(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/locations/search", params={"q": "zzzzzzzz"})
    assert response.status_code == 200 and response.json()["items"] == []
