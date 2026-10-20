"""Adding and managing job boards through the API: preview, credential, filters (ADR-049, T9.4)."""

from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.factories import make_intent, make_profile
from tests.fake_adapter import FakeAdapter

from jobs_radar.adapters.sources import catalogue
from jobs_radar.adapters.sources.base import BoardInfo, SourceError
from jobs_radar.core.crypto import CredentialBox
from jobs_radar.db.models import SearchIntent, SourceConfiguration
from jobs_radar.domain.enums import SourceErrorClass, SourceType

pytestmark = pytest.mark.integration

KEY = "itjobs-key-must-never-appear"


@pytest_asyncio.fixture(autouse=True)
async def _clean_world(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """No sources or intents from other tests; remove what this test leaves behind."""
    async with session_factory() as session:
        await session.execute(update(SearchIntent).values(enabled=False))
        await session.execute(update(SourceConfiguration).values(enabled=False))
        for source in (
            await session.execute(
                select(SourceConfiguration).where(
                    SourceConfiguration.source_type.in_(["himalayas", "itjobs_pt", "jobicy"])
                )
            )
        ).scalars():
            await session.delete(source)
        await session.commit()
    yield
    async with session_factory() as session:
        await session.execute(update(SearchIntent).values(enabled=False))
        for source in (
            await session.execute(
                select(SourceConfiguration).where(
                    SourceConfiguration.source_type.in_(["himalayas", "itjobs_pt", "jobicy"])
                )
            )
        ).scalars():
            await session.delete(source)
        await session.commit()


async def enable_an_intent(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        profile, _ = await make_profile(session)
        intent, _ = await make_intent(session, profile)
        intent.enabled = True
        await session.commit()


def use_adapters(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, adapter: FakeAdapter
) -> FakeAdapter:
    monkeypatch.setattr(
        app.state,
        "adapters",
        {SourceType.HIMALAYAS: adapter, SourceType.ITJOBS_PT: adapter},
    )
    return adapter


@pytest.fixture
def itjobs_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the key-requiring board addable, as it will be once its adapter is finished."""
    entry = catalogue.require_entry("itjobs_pt")
    monkeypatch.setitem(catalogue._BY_KEY, "itjobs_pt", replace(entry, available=True))
    monkeypatch.setattr(
        catalogue,
        "CATALOGUE",
        tuple(
            replace(e, available=True) if e.source_type is SourceType.ITJOBS_PT else e
            for e in catalogue.CATALOGUE
        ),
    )


def body(key: str = "himalayas", **extra: Any) -> dict[str, Any]:
    return {"source_type": key, "external_identifier": key, **extra}


# --- preview ---------------------------------------------------------------------------------------


async def test_preview_counts_matches_with_the_derived_scope_and_saves_nothing(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await enable_an_intent(session_factory)
    adapter = use_adapters(
        app,
        monkeypatch,
        FakeAdapter(
            board=BoardInfo("Himalayas", 1398, matching_count=212, matching_is_lower_bound=True)
        ),
    )
    response = await client.post(
        "/api/v1/sources/preview",
        json={"catalogue_key": "himalayas", "filters": {"max_age_days": 7}},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "display_name": "Himalayas",
        "postings_total": 1398,
        "postings_matching": 212,
        "matching_is_lower_bound": True,
    }
    identifier, credential, filters, scope = adapter.validations[0]
    assert (identifier, credential) == ("himalayas", None)
    assert filters is not None and filters.max_age_days == 7
    assert scope is not None and {"PT", "GB"} <= scope.country_codes
    listed = (await client.get("/api/v1/sources")).json()["items"]
    assert not [s for s in listed if s["source_type"] == "himalayas"]


async def test_preview_needs_a_location_from_the_profile(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_adapters(app, monkeypatch, FakeAdapter())
    response = await client.post("/api/v1/sources/preview", json={"catalogue_key": "himalayas"})
    assert response.status_code == 422
    assert response.json()["error"]["details"]["error_class"] == "configuration"
    assert "Profile & intent" in response.json()["error"]["message"]


@pytest.mark.parametrize("key", ["greenhouse", "nope"])
async def test_preview_refuses_keys_that_are_not_available_job_boards(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    key: str,
) -> None:
    await enable_an_intent(session_factory)
    use_adapters(app, monkeypatch, FakeAdapter())
    response = await client.post("/api/v1/sources/preview", json={"catalogue_key": key})
    assert response.status_code == 422


# --- adding -----------------------------------------------------------------------------------------


async def test_a_keyless_job_board_is_added_from_the_catalogue(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await enable_an_intent(session_factory)
    use_adapters(app, monkeypatch, FakeAdapter(board=BoardInfo("Himalayas", 10, matching_count=3)))
    response = await client.post("/api/v1/sources", json=body(filters={"max_age_days": 14}))
    assert response.status_code == 201, response.text
    source = response.json()
    assert source["category"] == "job_board"
    assert source["display_name"] == "Himalayas"
    assert source["company_id"] is None and source["company_name"] is None
    assert source["url"] == catalogue.require_entry("himalayas").endpoint
    assert source["filters"]["max_age_days"] == 14
    assert source["credential_status"] == "not_needed"
    assert (
        source["rate_limit_per_minute"]
        == catalogue.require_entry("himalayas").rate_limit_per_minute
    )
    again = await client.post("/api/v1/sources", json=body())
    assert again.status_code == 409


async def test_a_job_board_needs_an_enabled_intent_to_be_added(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_adapters(app, monkeypatch, FakeAdapter())
    response = await client.post("/api/v1/sources", json=body())
    assert response.status_code == 422
    assert response.json()["error"]["details"]["error_class"] == "configuration"


async def test_a_board_that_needs_a_key_is_checked_stored_encrypted_and_never_returned(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    itjobs_available: None,
) -> None:
    await enable_an_intent(session_factory)
    adapter = use_adapters(
        app, monkeypatch, FakeAdapter(board=BoardInfo("ITJobs.pt", 50, matching_count=9))
    )
    response = await client.post("/api/v1/sources", json=body("itjobs_pt", credential=KEY))
    assert response.status_code == 201, response.text
    source = response.json()
    assert source["credential_status"] == "saved"
    assert source["credential_updated_at"] is not None
    assert KEY not in response.text
    assert adapter.validations[0][1] == KEY  # the key was checked against the service
    listed = await client.get("/api/v1/sources")
    assert KEY not in listed.text
    async with session_factory() as session:
        row = (
            await session.execute(
                select(SourceConfiguration).where(
                    SourceConfiguration.source_configuration_id == source["source_configuration_id"]
                )
            )
        ).scalar_one()
        assert row.credential_ciphertext is not None
        assert KEY.encode() not in row.credential_ciphertext
        assert KEY not in row.url and KEY not in str(row.config_json)
        box = CredentialBox(SecretStr(app.state.settings.credential_key.get_secret_value()))
        assert box.decrypt(row.credential_ciphertext) == KEY


async def test_a_missing_or_unneeded_key_is_refused(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    itjobs_available: None,
) -> None:
    await enable_an_intent(session_factory)
    use_adapters(app, monkeypatch, FakeAdapter())
    assert (await client.post("/api/v1/sources", json=body("itjobs_pt"))).status_code == 422
    assert (
        await client.post("/api/v1/sources", json=body("himalayas", credential=KEY))
    ).status_code == 422


async def test_a_refused_key_saves_nothing(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    itjobs_available: None,
) -> None:
    await enable_an_intent(session_factory)
    refused = SourceError(
        SourceErrorClass.AUTHENTICATION, "The source refused the credential.", http_status=401
    )
    use_adapters(app, monkeypatch, FakeAdapter(board=refused))
    response = await client.post("/api/v1/sources", json=body("itjobs_pt", credential=KEY))
    assert response.status_code == 422
    assert response.json()["error"]["details"]["error_class"] == "authentication"
    assert KEY not in response.text
    listed = (await client.get("/api/v1/sources")).json()["items"]
    assert not [s for s in listed if s["source_type"] == "itjobs_pt"]


async def test_an_unavailable_board_cannot_be_added(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await enable_an_intent(session_factory)
    use_adapters(app, monkeypatch, FakeAdapter())
    entry = catalogue.require_entry("itjobs_pt")
    monkeypatch.setitem(catalogue._BY_KEY, "itjobs_pt", replace(entry, available=False))
    response = await client.post("/api/v1/sources", json=body("itjobs_pt", credential=KEY))
    assert response.status_code == 422


async def test_a_company_board_can_opt_in_to_filters_and_opt_out_again(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.factories import unique

    monkeypatch.setattr(app.state, "adapters", {SourceType.GREENHOUSE: FakeAdapter()})
    created = await client.post(
        "/api/v1/sources",
        json={"source_type": "greenhouse", "external_identifier": unique("filter-co")},
    )
    assert created.status_code == 201, created.text
    source = created.json()
    assert source["filters"] is None  # no filters: every posting is kept
    sid = source["source_configuration_id"]
    turned_on = await client.put(
        f"/api/v1/sources/{sid}",
        json={"expected_version": source["version"], "filters": {"categories": ["software"]}},
    )
    assert turned_on.status_code == 200, turned_on.text
    assert turned_on.json()["filters"]["categories"] == ["software"]
    turned_off = await client.put(
        f"/api/v1/sources/{sid}",
        json={"expected_version": turned_on.json()["version"], "clear_filters": True},
    )
    assert turned_off.status_code == 200
    assert turned_off.json()["filters"] is None


async def test_job_board_filters_cannot_be_cleared(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await enable_an_intent(session_factory)
    use_adapters(app, monkeypatch, FakeAdapter())
    source = (await client.post("/api/v1/sources", json=body())).json()
    response = await client.put(
        f"/api/v1/sources/{source['source_configuration_id']}",
        json={"expected_version": source["version"], "clear_filters": True},
    )
    assert response.status_code == 422


# --- the owner's areas (ADR-080, phase 5) ----------------------------------------------------------------

FIVE_AREAS = ["software", "data", "devops", "security", "telecom"]


async def test_the_catalogue_offers_the_areas_of_the_owners_packs(
    client: httpx.AsyncClient,
) -> None:
    items = (await client.get("/api/v1/source-catalogue")).json()["items"]
    assert items
    for item in items:
        assert item["available_categories"] == FIVE_AREAS  # the test owner has the software pack
        assert item["default_filters"]["categories"] == FIVE_AREAS


async def test_preview_passes_the_owners_rules_and_areas_to_the_board(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await enable_an_intent(session_factory)
    adapter = use_adapters(app, monkeypatch, FakeAdapter(board=BoardInfo("Himalayas", 10, 3)))
    response = await client.post(
        "/api/v1/sources/preview",
        json={"catalogue_key": "himalayas", "filters": {"max_age_days": 7}},
    )
    assert response.status_code == 200, response.text
    _identifier, _credential, filters, _scope = adapter.validations[0]
    assert filters is not None and filters.categories == FIVE_AREAS  # none named: the owner's areas
    rules = adapter.rules_seen[0]
    assert rules is not None and [a.key for a in rules.areas] == FIVE_AREAS


async def test_areas_the_owner_names_are_kept_as_they_are(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await enable_an_intent(session_factory)
    adapter = use_adapters(app, monkeypatch, FakeAdapter(board=BoardInfo("Himalayas", 10, 3)))
    await client.post(
        "/api/v1/sources/preview",
        json={"catalogue_key": "himalayas", "filters": {"categories": ["data"]}},
    )
    assert adapter.validations[0][2].categories == ["data"]  # type: ignore[union-attr]
    await client.post(
        "/api/v1/sources/preview",
        json={"catalogue_key": "himalayas", "filters": {"categories": []}},
    )
    assert adapter.validations[1][2].categories == []  # type: ignore[union-attr]
