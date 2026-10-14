"""GET /companies (T7.1, ADR-053)."""

import httpx
import pytest

pytestmark = pytest.mark.integration


async def test_the_company_list_has_counts_total_and_the_threshold(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/companies", params={"limit": 5})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "items",
        "total",
        "sort",
        "search_intent_id",
        "relevance_min_score",
        "recency_days",
    }
    assert body["sort"] == "newest" and body["relevance_min_score"] == 45
    assert body["recency_days"] == 30
    if body["items"]:
        assert set(body["items"][0]) == {
            "company_id",
            "name",
            "homepage_url",
            "careers_url",
            "employer_type",
            "open_offers",
            "recommended_offers",
            "best_fit_score",
            "pending_candidates",
            "is_followed",
            "is_ignored",
            "has_source",
        }


async def test_the_filters_are_accepted(client: httpx.AsyncClient) -> None:
    params = {
        "followed_only": True,
        "open_only": True,
        "recommended_only": True,
        "pending_only": True,
        "sort": "name",
    }
    assert (await client.get("/api/v1/companies", params=params)).status_code == 200


async def test_bad_parameters_are_422(client: httpx.AsyncClient) -> None:
    for params in ({"sort": "random"}, {"limit": 0}, {"relevance_min_score": 101}):
        assert (await client.get("/api/v1/companies", params=params)).status_code == 422
