"""AI & privacy API: write-only credentials, safe projections and no secret in logs (T6.1-T6.3)."""

import json
import logging
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.adapters.providers.factory import ProviderSpec
from jobs_radar.db.models import PrivacySetting, ProviderConnection
from jobs_radar.domain.enums import ProviderErrorClass

pytestmark = pytest.mark.integration

SECRET = "sk-api-secret-must-never-appear"
BASE = "/api/v1/settings"


class Lister:
    def __init__(self, spec: ProviderSpec) -> None:
        self.spec = spec

    async def available_models(self) -> list[str]:
        if self.spec.api_key == "bad":
            raise ProviderError(
                ProviderErrorClass.UNAUTHORIZED, "The AI provider refused the credential."
            )
        return ["m-1", "m-2"]


async def _resolve(host: str) -> list[str]:
    return ["93.184.216.34"]


@pytest_asyncio.fixture(autouse=True)
async def clean(
    session_factory: async_sessionmaker[AsyncSession], app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[None]:
    monkeypatch.setattr(app.state, "provider_builder", Lister, raising=False)
    monkeypatch.setattr(app.state, "url_resolver", _resolve, raising=False)

    async def wipe() -> None:
        async with session_factory() as session:
            await session.execute(delete(ProviderConnection))
            await session.execute(delete(PrivacySetting))
            await session.commit()

    await wipe()
    yield
    await wipe()


async def new_connection(client: httpx.AsyncClient, **overrides: object) -> dict[str, object]:
    body = {
        "provider_type": "openai",
        "display_name": "OpenAI",
        "model_id": "gpt-test",
        **overrides,
    }
    response = await client.post(f"{BASE}/ai/connections", json=body)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def test_the_projection_shows_a_credential_status_and_never_the_credential(
    client: httpx.AsyncClient,
) -> None:
    connection = await new_connection(client)
    cid = connection["provider_connection_id"]
    saved = await client.put(f"{BASE}/ai/connections/{cid}/credential", json={"secret": SECRET})
    assert saved.status_code == 200 and SECRET not in saved.text
    assert saved.json()["credential_status"] == "saved"
    body = (await client.get(f"{BASE}/ai")).text
    assert (
        SECRET not in body
        and "ciphertext" not in body
        and "secret" not in body.replace("credential_status", "")
    )
    data = json.loads(body)
    assert data["mode"] == "no_ai" and data["key_configured"] is True
    assert data["privacy"]["redact_contact_details"] is True
    row = data["connections"][0]
    assert row["credential_status"] == "saved" and "credential_updated_at" in row

    cleared = await client.delete(f"{BASE}/ai/connections/{cid}/credential")
    assert cleared.json()["credential_status"] == "none"


async def test_the_credential_endpoint_is_write_only(client: httpx.AsyncClient) -> None:
    cid = (await new_connection(client))["provider_connection_id"]
    assert (await client.get(f"{BASE}/ai/connections/{cid}/credential")).status_code in {404, 405}
    assert (
        await client.put(f"{BASE}/ai/connections/{cid}/credential", json={"secret": " "})
    ).status_code == 422
    assert (
        await client.put(f"{BASE}/ai/connections/{cid}/credential", json={"secret": SECRET, "x": 1})
    ).status_code == 422


async def test_a_validation_error_never_echoes_the_submitted_secret(
    client: httpx.AsyncClient,
) -> None:
    cid = (await new_connection(client))["provider_connection_id"]
    response = await client.put(
        f"{BASE}/ai/connections/{cid}/credential", json={"secret": SECRET, "extra": 1}
    )
    assert response.status_code == 422 and SECRET not in response.text


async def test_the_secret_is_not_logged(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    cid = (await new_connection(client))["provider_connection_id"]
    with caplog.at_level(logging.DEBUG):
        await client.put(f"{BASE}/ai/connections/{cid}/credential", json={"secret": SECRET})
        await client.post(f"{BASE}/ai/connections/{cid}/test")
    assert SECRET not in caplog.text


async def test_unsafe_endpoints_are_422_and_unknown_connections_404(
    client: httpx.AsyncClient,
) -> None:
    bad = await client.post(
        f"{BASE}/ai/connections",
        json={
            "provider_type": "compatible",
            "display_name": "x",
            "endpoint_url": "http://insecure.test/v1",
        },
    )
    assert bad.status_code == 422
    assert (await client.delete(f"{BASE}/ai/connections/999999")).status_code == 404


async def test_a_connection_test_and_activation_flow(client: httpx.AsyncClient) -> None:
    cid = (await new_connection(client))["provider_connection_id"]
    assert (
        await client.post(f"{BASE}/ai/connections/{cid}/test")
    ).status_code == 422  # no credential yet
    await client.put(f"{BASE}/ai/connections/{cid}/credential", json={"secret": SECRET})
    tested = (await client.post(f"{BASE}/ai/connections/{cid}/test")).json()
    assert tested == {
        "ok": True,
        "error_class": None,
        "message": "Connected; 2 models available.",
        "models": ["m-1", "m-2"],
    }

    assert (
        await client.put(f"{BASE}/ai/import-connection", json={"provider_connection_id": cid})
    ).status_code == 200
    assert (await client.get(f"{BASE}/ai")).json()["mode"] == "remote"
    assert (
        await client.put(f"{BASE}/ai/jobs-connection", json={"provider_connection_id": cid})
    ).status_code == 422
    await client.put(f"{BASE}/ai/import-connection", json={"provider_connection_id": None})
    assert (await client.get(f"{BASE}/ai")).json()["mode"] == "no_ai"


async def test_a_failed_test_is_reported_not_raised(client: httpx.AsyncClient) -> None:
    cid = (await new_connection(client))["provider_connection_id"]
    await client.put(f"{BASE}/ai/connections/{cid}/credential", json={"secret": "bad"})
    tested = await client.post(f"{BASE}/ai/connections/{cid}/test")
    assert tested.status_code == 200 and tested.json()["ok"] is False
    assert tested.json()["error_class"] == "unauthorized"


async def test_metadata_updates_need_the_version_and_privacy_is_editable(
    client: httpx.AsyncClient,
) -> None:
    created = await new_connection(client)
    cid, version = created["provider_connection_id"], created["version"]
    ok = await client.put(
        f"{BASE}/ai/connections/{cid}",
        json={"display_name": "Renamed", "model_id": "m-2", "expected_version": version},
    )
    assert ok.status_code == 200 and ok.json()["display_name"] == "Renamed"
    stale = await client.put(
        f"{BASE}/ai/connections/{cid}", json={"display_name": "x", "expected_version": version}
    )
    assert stale.status_code == 409

    privacy = (await client.get(f"{BASE}/ai")).json()["privacy"]
    changed = await client.put(
        f"{BASE}/privacy",
        json={"redact_contact_details": False, "expected_version": privacy["version"]},
    )
    assert changed.status_code == 200 and changed.json()["redact_contact_details"] is False


async def test_local_providers_can_be_allowed_from_the_privacy_settings(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A developer's .env may allow it already; this test is about the owner's switch.
    off = app.state.settings.model_copy(update={"allow_local_providers": False})
    monkeypatch.setattr(app.state, "settings", off)
    before = (await client.get(f"{BASE}/ai")).json()["privacy"]
    assert before["allow_local_providers"] is False
    assert before["local_providers_forced_by_environment"] is False
    changed = await client.put(
        f"{BASE}/privacy",
        json={
            "redact_contact_details": before["redact_contact_details"],
            "allow_local_providers": True,
            "expected_version": before["version"],
        },
    )
    assert changed.status_code == 200 and changed.json()["allow_local_providers"] is True
    created = await new_connection(client, provider_type="ollama")
    assert created["processing_location"] == "local"
