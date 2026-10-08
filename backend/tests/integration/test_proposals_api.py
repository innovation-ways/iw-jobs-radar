"""CV import end to end through the API: upload, consent, proposal, review, revision N+1 (T6.5)."""

import json
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.document_files import text_bytes

from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderOutput
from jobs_radar.adapters.providers.factory import ProviderSpec
from jobs_radar.db.models import PrivacySetting, ProviderConnection

pytestmark = pytest.mark.integration

SECRET = "sk-api-import-secret"
BASE = "/api/v1"
CV = [
    "Alex Example",
    "Senior Software Engineer with 9 years of experience.",
    "Email alex.example@example.test, phone +351 912 345 678, https://linkedin.com/in/alex",
    "Lives in Lisbon, Portugal. Skills: Python (expert, 8 years), Docker.",
]
ANSWER = json.dumps(
    {
        "items": [
            {
                "path": "headline",
                "value": "Senior Software Engineer",
                "excerpt": "Senior Software Engineer",
                "confidence": 0.9,
            },
            {
                "path": "years_experience",
                "value": 9,
                "excerpt": "9 years of experience",
                "confidence": 0.8,
            },
            {
                "path": "base_location",
                "value": {"place": "Lisbon", "country": "PT"},
                "excerpt": "Lisbon, Portugal",
                "confidence": 0.8,
            },
            {
                "path": "skills",
                "value": {"name": "Python", "level": "expert", "years": 8},
                "excerpt": "Python (expert, 8 years)",
                "confidence": 0.9,
            },
        ]
    }
)
sent: list[ExtractionRequest] = []


class Chat:
    def __init__(self, spec: ProviderSpec) -> None:
        self.spec, self.provider, self.model = spec, spec.provider_type, spec.model

    async def extract(self, request: ExtractionRequest) -> ProviderOutput:
        sent.append(request)
        return ProviderOutput(content=ANSWER, latency_ms=3)

    async def available_models(self) -> list[str]:
        return [self.model]


async def _resolve(host: str) -> list[str]:
    return ["93.184.216.34"]


@pytest_asyncio.fixture(autouse=True)
async def clean(
    session_factory: async_sessionmaker[AsyncSession], app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[None]:
    monkeypatch.setattr(app.state, "provider_builder", Chat, raising=False)
    monkeypatch.setattr(app.state, "url_resolver", _resolve, raising=False)
    sent.clear()

    async def wipe() -> None:
        async with session_factory() as session:
            await session.execute(delete(ProviderConnection))
            await session.execute(delete(PrivacySetting))
            await session.commit()

    await wipe()
    yield
    await wipe()


async def remote_connection(client: httpx.AsyncClient) -> dict[str, object]:
    created = (
        await client.post(
            f"{BASE}/settings/ai/connections",
            json={"provider_type": "openai", "display_name": "OpenAI", "model_id": "gpt-test"},
        )
    ).json()
    cid = created["provider_connection_id"]
    await client.put(f"{BASE}/settings/ai/connections/{cid}/credential", json={"secret": SECRET})
    assert (
        await client.put(
            f"{BASE}/settings/ai/import-connection", json={"provider_connection_id": cid}
        )
    ).status_code == 200
    return created  # type: ignore[no-any-return]


async def new_profile(client: httpx.AsyncClient) -> int:
    return int(
        (await client.post(f"{BASE}/profiles", json={"title": "Imported"})).json()[
            "career_profile_id"
        ]
    )


async def upload(client: httpx.AsyncClient) -> int:
    response = await client.post(
        f"{BASE}/documents", files={"file": ("cv.txt", text_bytes(CV), "text/plain")}
    )
    return int(response.json()["document_id"])


async def test_the_whole_import_flow_creates_revision_one_and_only_redacted_text_leaves(
    client: httpx.AsyncClient,
) -> None:
    connection = await remote_connection(client)
    profile_id, document_id = await new_profile(client), await upload(client)
    consent = {
        "provider_connection_id": connection["provider_connection_id"],
        "model_id": "gpt-test",
    }

    # no consent: refused, nothing was sent
    refused = await client.post(
        f"{BASE}/documents/{document_id}/proposals", json={"career_profile_id": profile_id}
    )
    assert (
        refused.status_code == 422
        and refused.json()["error"]["details"]["error_class"] == "consent_required"
    )
    assert sent == []

    created = await client.post(
        f"{BASE}/documents/{document_id}/proposals",
        json={"career_profile_id": profile_id, "consent": consent},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["provider_type"], body["provider_model"], body["redaction_policy"]) == (
        "openai",
        "gpt-test",
        "contact-v1",
    )
    assert SECRET not in created.text and "example.test" not in created.text
    assert "alex.example@example.test" not in sent[0].user and "[EMAIL]" in sent[0].user
    assert [i["path"] for i in body["items"]] == [
        "headline",
        "years_experience",
        "base_location",
        "skills",
    ]
    assert all(i["review_status"] == "pending" for i in body["items"])

    fetched = (await client.get(f"{BASE}/proposals/{body['profile_proposal_id']}")).json()
    assert fetched["profile_proposal_id"] == body["profile_proposal_id"]

    decisions = [
        {"proposal_item_id": i["proposal_item_id"], "decision": "accept"} for i in body["items"]
    ]
    reviewed = await client.post(
        f"{BASE}/profiles/{profile_id}/reviews",
        json={
            "profile_proposal_id": body["profile_proposal_id"],
            "expected_current_revision": None,
            "decisions": decisions,
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    result = reviewed.json()
    assert (
        result["created"] is True and result["profile"]["current_revision"]["revision_number"] == 1
    )
    facts = result["profile"]["current_revision"]["facts"]
    assert (
        facts["headline"] == "Senior Software Engineer"
        and facts["base_location"]["timezone"] == "Europe/Lisbon"
    )
    assert facts["skills"][0]["provenance"]["origin"] == "document"
    assert result["proposal"]["status"] == "completed"

    # the same decisions again are a conflict, not a second revision
    again = await client.post(
        f"{BASE}/profiles/{profile_id}/reviews",
        json={
            "profile_proposal_id": body["profile_proposal_id"],
            "expected_current_revision": 1,
            "decisions": decisions,
        },
    )
    assert again.status_code == 409


async def test_without_an_ai_connection_the_proposal_is_422(client: httpx.AsyncClient) -> None:
    profile_id, document_id = await new_profile(client), await upload(client)
    response = await client.post(
        f"{BASE}/documents/{document_id}/proposals", json={"career_profile_id": profile_id}
    )
    assert response.status_code == 422 and sent == []


async def test_unknown_documents_proposals_and_bad_bodies(client: httpx.AsyncClient) -> None:
    profile_id = await new_profile(client)
    assert (
        await client.post(
            f"{BASE}/documents/999999/proposals", json={"career_profile_id": profile_id}
        )
    ).status_code == 404
    assert (await client.get(f"{BASE}/proposals/999999")).status_code == 404
    bad = await client.post(
        f"{BASE}/profiles/{profile_id}/reviews",
        json={
            "profile_proposal_id": 1,
            "expected_current_revision": None,
            "decisions": [{"proposal_item_id": 1, "decision": "maybe"}],
        },
    )
    assert bad.status_code == 422
