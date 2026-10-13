"""Evaluation endpoints (T4.6): on-demand scoring, reading an evaluation and re-scoring."""

from copy import deepcopy
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.data import sample_intent
from tests.evaluation_world import World, world

pytestmark = pytest.mark.integration

API = "/api/v1"


async def committed_world(session_factory: async_sessionmaker[AsyncSession]) -> World:
    """The synthetic world, committed so the API (its own session) can see it."""
    async with session_factory() as session:
        w = await world(session)
        await session.commit()
        return w


def body(w: World, **changes: Any) -> dict[str, Any]:
    return {
        "profile_revision_id": w.profile_revision_id,
        "intent_revision_id": w.intent_revision_id,
        "policy_version": "matching-v1.6",
        **changes,
    }


async def test_evaluating_a_posting_returns_the_score_with_its_dimensions_and_inputs(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    w = await committed_world(session_factory)
    response = await client.post(f"{API}/jobs/{w.posting.job_posting_id}/evaluations", json=body(w))
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["policy_version"] == "matching-v1.6"
    assert result["job_source_hash"].startswith("sha256:")
    assert (result["profile_revision_id"], result["intent_revision_id"]) == (
        w.profile_revision_id,
        w.intent_revision_id,
    )
    assert 0 <= result["fit_score"] <= 100
    assert result["fit_band"] in {"excellent", "strong", "average", "low", "not_recommended"}
    assert result["recommendation"] in {"recommended", "not_recommended"}
    keys = [d["dimension_key"] for d in result["dimensions"]]
    assert keys[:3] == ["role_responsibilities", "skills_technology", "work_arrangement_location"]
    assert len(keys) == 11
    work = next(
        d for d in result["dimensions"] if d["dimension_key"] == "work_arrangement_location"
    )
    assert work["status"] == "match" and work["evidence"]["job_quote"]
    assert work["explanation"]
    assert result["weights"]["role_responsibilities"] == 25


async def test_evaluating_twice_returns_the_same_evaluation(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    w = await committed_world(session_factory)
    first = await client.post(f"{API}/jobs/{w.posting.job_posting_id}/evaluations", json=body(w))
    second = await client.post(f"{API}/jobs/{w.posting.job_posting_id}/evaluations", json=body(w))
    assert second.status_code in (200, 201)
    assert first.json()["match_evaluation_id"] == second.json()["match_evaluation_id"]


async def test_an_evaluation_can_be_read_back(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    w = await committed_world(session_factory)
    created = (
        await client.post(f"{API}/jobs/{w.posting.job_posting_id}/evaluations", json=body(w))
    ).json()
    fetched = await client.get(f"{API}/evaluations/{created['match_evaluation_id']}")
    assert fetched.status_code == 200 and fetched.json() == created
    assert (await client.get(f"{API}/evaluations/987654321")).status_code == 404


@pytest.mark.parametrize(
    ("changes", "status"),
    [
        ({"policy_version": "matching-v2"}, 422),
        ({"profile_revision_id": 987654321}, 404),
        ({"intent_revision_id": 987654321}, 404),
        ({"unexpected": 1}, 422),
    ],
)
async def test_invalid_evaluation_requests_are_rejected(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    changes: dict[str, Any],
    status: int,
) -> None:
    w = await committed_world(session_factory)
    response = await client.post(
        f"{API}/jobs/{w.posting.job_posting_id}/evaluations", json=body(w, **changes)
    )
    assert response.status_code == status


async def test_an_unknown_posting_is_not_found_and_an_unextracted_one_conflicts(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    w = await committed_world(session_factory)
    assert (await client.post(f"{API}/jobs/987654321/evaluations", json=body(w))).status_code == 404
    from sqlalchemy import update

    from jobs_radar.db.models import (
        JobExtraction,
        JobSnapshot,  # noqa: F401
    )

    async with session_factory() as session:
        # a posting whose only extraction is not finished is "not evaluated"
        from tests.factories import make_company, make_posting, make_source

        source = await make_source(session, await make_company(session))
        posting, snapshot = await make_posting(session, source)
        session.add(
            JobExtraction(
                job_snapshot_id=snapshot.job_snapshot_id,
                status="pending",
                provider="p",
                model="m",
                prompt_version="extract-v2",
                taxonomy_version_id=1,
            )
        )
        await session.commit()
        posting_id = posting.job_posting_id
    response = await client.post(f"{API}/jobs/{posting_id}/evaluations", json=body(w))
    assert response.status_code == 409
    assert "extract" in response.json()["error"]["message"]
    del update


async def test_rescoring_scores_existing_jobs_under_the_new_revision_without_ai(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    w = await committed_world(session_factory)
    first = (
        await client.post(f"{API}/jobs/{w.posting.job_posting_id}/evaluations", json=body(w))
    ).json()
    changed = deepcopy(sample_intent())
    changed["weights"]["compensation"] = 30
    save = await client.put(
        f"{API}/intents/{w.intent_id}", json={**changed, "expected_current_revision": 1}
    )
    assert save.json()["created"] is True

    result = await client.post(f"{API}/intents/{w.intent_id}/rescore")
    assert result.status_code == 200
    assert result.json()["evaluated"] >= 1
    again = await client.post(f"{API}/intents/{w.intent_id}/rescore")
    assert again.json()["evaluated"] == 0
    assert first["weights"]["compensation"] == 10
    assert (await client.post(f"{API}/intents/987654321/rescore")).status_code == 404
