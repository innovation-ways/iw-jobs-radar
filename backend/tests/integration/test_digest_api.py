"""GET /digests/daily (T5.4)."""

import httpx
import pytest

pytestmark = pytest.mark.integration


async def test_the_daily_digest_has_its_three_sections_and_counts(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/digests/daily")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "generated_at",
        "since",
        "search_intent_id",
        "alert_threshold",
        "new_high_fit",
        "changed_shortlisted",
        "source_health",
        "last_run",
        "counts",
    }
    assert set(body["counts"]) == {
        "new_high_fit",
        "changed_shortlisted",
        "sources_needing_attention",
    }
    assert isinstance(body["new_high_fit"], list) and isinstance(body["source_health"], list)


async def test_an_unknown_intent_is_404(client: httpx.AsyncClient) -> None:
    assert (
        await client.get("/api/v1/digests/daily", params={"search_intent_id": 999999})
    ).status_code == 404
