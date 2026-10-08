"""GET /companies (T7.1)."""

import httpx
import pytest

pytestmark = pytest.mark.integration


async def test_the_company_list_has_counts_total_and_the_threshold(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/companies", params={"window": 30, "limit": 5})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "items",
        "total",
        "window",
        "sort",
        "search_intent_id",
        "relevance_min_score",
    }
    assert body["window"] == 30 and body["relevance_min_score"] == 45
    if body["items"]:
        assert set(body["items"][0]) == {
            "company_id",
            "name",
            "homepage_url",
            "careers_url",
            "employer_type",
            "open_offers",
            "new_offers_7d",
            "new_offers_15d",
            "new_offers_30d",
            "relevant_new_offers_7d",
            "relevant_new_offers_15d",
            "relevant_new_offers_30d",
        }


async def test_bad_parameters_are_422(client: httpx.AsyncClient) -> None:
    for params in ({"window": 10}, {"sort": "random"}, {"limit": 0}, {"relevance_min_score": 101}):
        assert (await client.get("/api/v1/companies", params=params)).status_code == 422
