"""Sources and collection-run endpoints (T2.5), with a scripted adapter and no network."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.factories import make_intent, make_profile, unique
from tests.fake_adapter import FakeAdapter, listing, make_posting

from jobs_radar.adapters.sources.base import BoardInfo, SourceError
from jobs_radar.db.models import SearchIntent, SourceConfiguration
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.services.collection import CollectionService

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def _only_this_tests_sources(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """Disable sources left by earlier tests so "all enabled sources" runs only see ours."""
    async with session_factory() as session:
        await session.execute(update(SourceConfiguration).values(enabled=False))
        await session.commit()
    yield


def use_adapter(app: FastAPI, monkeypatch: pytest.MonkeyPatch, adapter: FakeAdapter) -> FakeAdapter:
    """Install a fake adapter for Greenhouse in the running application."""
    monkeypatch.setattr(app.state, "adapters", {SourceType.GREENHOUSE: adapter})
    return adapter


async def add_source(client: httpx.AsyncClient, **overrides: Any) -> dict[str, Any]:
    body = {"source_type": "greenhouse", "external_identifier": unique("board"), **overrides}
    response = await client.post("/api/v1/sources", json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def settle(app: FastAPI) -> None:
    """Run what is queued, as the worker does (the API only queues runs)."""
    await CollectionService(app.state.session_factory, app.state.adapters).run_queued()


# --- sources ------------------------------------------------------------------------------------


async def test_adding_a_board_returns_the_source_with_its_company(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_adapter(app, monkeypatch, FakeAdapter(board=BoardInfo("Acme Robotics", 4)))
    source = await add_source(client)
    assert source["display_name"] == "Acme Robotics"
    assert source["company_name"] == "Acme Robotics"
    assert source["source_type"] == "greenhouse"
    assert source["enabled"] is True
    assert source["version"] == 1
    assert source["open_postings"] == 0
    assert source["last_result"] is None
    assert source["url"].startswith("https://boards.example.test/")
    assert not {"credential", "credential_ciphertext", "etag"} & source.keys()


async def test_a_board_can_be_added_disabled(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_adapter(app, monkeypatch, FakeAdapter())
    assert (await add_source(client, enabled=False))["enabled"] is False


async def test_adding_the_same_board_twice_conflicts(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_adapter(app, monkeypatch, FakeAdapter())
    source = await add_source(client)
    again = await client.post(
        "/api/v1/sources",
        json={"source_type": "greenhouse", "external_identifier": source["external_identifier"]},
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "conflict"


@pytest.mark.parametrize(
    ("failure", "status", "error_class"),
    [
        (
            SourceError(SourceErrorClass.NOT_FOUND, "The board was not found.", http_status=404),
            422,
            "not_found",
        ),
        (
            SourceError(SourceErrorClass.TIMEOUT, "The source did not answer in time."),
            503,
            "timeout",
        ),
    ],
)
async def test_a_board_that_cannot_be_validated_returns_a_classified_error(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    failure: SourceError,
    status: int,
    error_class: str,
) -> None:
    use_adapter(app, monkeypatch, FakeAdapter(board=failure))
    response = await client.post(
        "/api/v1/sources", json={"source_type": "greenhouse", "external_identifier": unique("x")}
    )
    assert response.status_code == status
    error = response.json()["error"]
    assert error["details"]["error_class"] == error_class
    assert error["message"] == failure.message


@pytest.mark.parametrize(
    "body",
    [
        {"source_type": "lever", "external_identifier": "x"},  # not supported yet
        {"source_type": "nonsense", "external_identifier": "x"},
        {"source_type": "greenhouse", "external_identifier": ""},
        {"source_type": "greenhouse"},
        {"source_type": "greenhouse", "external_identifier": "x", "credential": "secret"},
    ],
)
async def test_invalid_source_input_is_rejected(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch, body: dict[str, Any]
) -> None:
    use_adapter(app, monkeypatch, FakeAdapter())
    response = await client.post("/api/v1/sources", json=body)
    assert response.status_code == 422


async def test_listing_shows_status_after_a_run(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_adapter(app, monkeypatch, FakeAdapter([listing(make_posting("1"), make_posting("2"))]))
    source = await add_source(client)
    run = await client.post(f"/api/v1/sources/{source['source_configuration_id']}/run")
    assert run.status_code == 202
    await settle(app)

    rows = (await client.get("/api/v1/sources")).json()["items"]
    row = next(r for r in rows if r["source_configuration_id"] == source["source_configuration_id"])
    assert row["open_postings"] == 2
    result = row["last_result"]
    assert result["outcome"] == "success"
    assert (result["collected_count"], result["new_count"]) == (2, 2)
    assert result["error_class"] is None and result["finished_at"] is not None


async def test_updating_a_source_uses_optimistic_concurrency(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_adapter(app, monkeypatch, FakeAdapter())
    source = await add_source(client)
    url = f"/api/v1/sources/{source['source_configuration_id']}"
    ok = await client.put(
        url, json={"expected_version": 1, "enabled": False, "rate_limit_per_minute": 3}
    )
    assert ok.status_code == 200
    assert (ok.json()["enabled"], ok.json()["rate_limit_per_minute"], ok.json()["version"]) == (
        False,
        3,
        2,
    )
    stale = await client.put(url, json={"expected_version": 1, "enabled": True})
    assert stale.status_code == 409
    missing = await client.put(
        "/api/v1/sources/987654321", json={"expected_version": 1, "enabled": True}
    )
    assert missing.status_code == 404
    too_fast = await client.put(url, json={"expected_version": 2, "rate_limit_per_minute": 0})
    assert too_fast.status_code == 422


# --- runs ---------------------------------------------------------------------------------------


async def test_running_one_source_queues_a_run_and_records_the_result(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_adapter(app, monkeypatch, FakeAdapter([listing(make_posting("1"))]))
    source = await add_source(client, enabled=False)  # a disabled source can still be run by hand
    response = await client.post(f"/api/v1/sources/{source['source_configuration_id']}/run")
    assert response.status_code == 202
    queued = response.json()
    assert queued["status"] == "queued"
    assert queued["source_configuration_id"] == source["source_configuration_id"]
    assert queued["results"] == []
    await settle(app)

    page = (await client.get("/api/v1/collection-runs?limit=5")).json()
    run = next(r for r in page["items"] if r["collection_run_id"] == queued["collection_run_id"])
    assert run["status"] == "succeeded" and run["trigger"] == "manual"
    assert run["finished_at"] is not None
    (result,) = run["results"]
    assert result["source_configuration_id"] == source["source_configuration_id"]
    assert result["new_count"] == 1


async def test_running_an_unknown_source_is_not_found(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/v1/sources/987654321/run")).status_code == 404


async def test_run_all_needs_an_enabled_source(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/collection-runs")
    assert response.status_code == 422
    assert "enabled" in response.json()["error"]["message"]


async def test_run_all_isolates_failures_and_reports_a_partial_run(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad_id = unique("bad")

    def provider(checkpoint: Any) -> object:
        if checkpoint.identifier == bad_id:
            return SourceError(
                SourceErrorClass.NOT_FOUND,
                "The board was not found. Check the board token.",
                http_status=404,
            )
        return listing(make_posting("7"))

    use_adapter(app, monkeypatch, FakeAdapter(provider=provider))
    bad = await add_source(client, external_identifier=bad_id)
    good = await add_source(client)

    response = await client.post("/api/v1/collection-runs")
    assert response.status_code == 202
    run_id = response.json()["collection_run_id"]
    await settle(app)

    page = (await client.get("/api/v1/collection-runs?limit=5")).json()
    run = next(r for r in page["items"] if r["collection_run_id"] == run_id)
    assert run["status"] == "partial"
    by_source = {r["source_configuration_id"]: r for r in run["results"]}
    assert by_source[good["source_configuration_id"]]["outcome"] == "success"
    failed = by_source[bad["source_configuration_id"]]
    assert (failed["outcome"], failed["error_class"], failed["http_status"]) == (
        "failed",
        "not_found",
        404,
    )
    assert failed["error_message"] == "The board was not found. Check the board token."


async def test_run_history_is_newest_first_and_paginated_by_cursor(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_adapter(app, monkeypatch, FakeAdapter(provider=lambda _c: listing(make_posting("1"))))
    source = await add_source(client)
    ids = []
    for _ in range(3):
        ids.append(
            (await client.post(f"/api/v1/sources/{source['source_configuration_id']}/run")).json()[
                "collection_run_id"
            ]
        )
        await settle(app)

    first = (await client.get("/api/v1/collection-runs?limit=2")).json()
    assert [r["collection_run_id"] for r in first["items"]] == [ids[2], ids[1]]
    assert first["next_before_collection_run_id"] == ids[1]
    second = (
        await client.get(f"/api/v1/collection-runs?limit=2&before_collection_run_id={ids[1]}")
    ).json()
    assert second["items"][0]["collection_run_id"] == ids[0]
    assert (await client.get("/api/v1/collection-runs?limit=0")).status_code == 422
    assert (await client.get("/api/v1/collection-runs?limit=101")).status_code == 422


async def test_a_crashing_run_does_not_break_the_api(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_adapter(app, monkeypatch, FakeAdapter([RuntimeError("boom 10.0.0.9")]))
    source = await add_source(client)
    await client.post(f"/api/v1/sources/{source['source_configuration_id']}/run")
    await settle(app)
    run = (await client.get("/api/v1/collection-runs?limit=1")).json()["items"][0]
    assert run["status"] == "failed"
    assert "10.0.0.9" not in str(run)
    assert (await client.get("/healthz")).status_code == 200


# --- job boards: catalogue and source fields (ADR-049, T9.1) -------------------------------------


async def test_the_catalogue_lists_the_available_job_boards_without_secrets(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/source-catalogue")
    assert response.status_code == 200
    items = {item["catalogue_key"]: item for item in response.json()["items"]}
    assert set(items) == {
        "arbeitnow",
        "jobicy",
        "himalayas",
        "itjobs_pt",
        "weworkremotely",
        "workingnomads",
        "remoteok",
        "freelancermap",
        "remotive",
    }
    assert items["itjobs_pt"]["requires_credential"] is True
    assert items["itjobs_pt"]["credential_label"] == "ITJobs API key"
    himalayas = items["himalayas"]
    assert himalayas["requires_credential"] is False
    assert himalayas["already_added"] is False
    assert "country_codes" not in himalayas["default_filters"]
    assert himalayas["default_filters"]["max_age_days"] == 4
    assert himalayas["terms_url"].startswith("https://")
    assert himalayas["available_categories"]
    assert not {"endpoint", "credential"} & himalayas.keys()


async def test_a_company_board_reports_its_category_and_no_filters(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_adapter(app, monkeypatch, FakeAdapter())
    source = await add_source(client)
    assert source["category"] == "company_board"
    assert source["filters"] is None
    assert source["credential_status"] == "not_needed"
    assert source["coverage_note"] is None
    assert source["terms_url"] is None
    assert source["attribution_text"] is None


async def test_the_source_scope_is_empty_without_an_enabled_intent(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        await session.execute(update(SearchIntent).values(enabled=False))
        await session.commit()
    response = await client.get("/api/v1/source-scope")
    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "country_codes": [],
        "include_worldwide": False,
        "any_country": False,
        "onsite_areas": [],
    }


async def test_the_source_scope_comes_from_the_profile_and_the_intent(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        await session.execute(update(SearchIntent).values(enabled=False))
        profile, _ = await make_profile(session)
        intent, _ = await make_intent(session, profile)
        intent.enabled = True
        await session.commit()
    try:
        body = (await client.get("/api/v1/source-scope")).json()
        assert body["configured"] is True
        assert {"PT", "GB"} <= set(body["country_codes"])  # base country, remote regions EU and UK
        assert body["include_worldwide"] is True
        assert body["onsite_areas"] == [{"place": "Lisbon, Portugal", "radius_km": 40}]
    finally:
        async with session_factory() as session:
            await session.execute(update(SearchIntent).values(enabled=False))
            await session.commit()


# --- other company boards (ADR-050) ----------------------------------------------------------------


async def test_a_lever_board_is_added_with_the_company_name_the_owner_typed(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = FakeAdapter(board=BoardInfo("Guessed Name", 3))
    monkeypatch.setattr(app.state, "adapters", {SourceType.LEVER: adapter})
    response = await client.post(
        "/api/v1/sources",
        json={
            "source_type": "lever",
            "external_identifier": unique("lever-co"),
            "display_name": "Real Company Ltd",
        },
    )
    assert response.status_code == 201, response.text
    source = response.json()
    assert source["category"] == "company_board"
    assert source["display_name"] == "Real Company Ltd"
    assert source["company_name"] == "Real Company Ltd"


async def test_without_a_typed_name_the_guessed_one_is_used(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app.state, "adapters", {SourceType.ASHBY: FakeAdapter(board=BoardInfo("Guessed Co", 1))}
    )
    response = await client.post(
        "/api/v1/sources", json={"source_type": "ashby", "external_identifier": unique("ashby-co")}
    )
    assert response.status_code == 201
    assert response.json()["display_name"] == "Guessed Co"


async def test_a_smartrecruiters_board_gets_a_faster_default_pace(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app.state,
        "adapters",
        {SourceType.SMARTRECRUITERS: FakeAdapter(board=BoardInfo("Synth", 9))},
    )
    response = await client.post(
        "/api/v1/sources",
        json={"source_type": "smartrecruiters", "external_identifier": unique("SynthCo")},
    )
    assert response.status_code == 201
    assert response.json()["rate_limit_per_minute"] == 30


async def test_an_eightfold_board_is_added_by_its_careers_address(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app.state, "adapters", {SourceType.EIGHTFOLD: FakeAdapter(board=BoardInfo("Synthco", 25))}
    )
    response = await client.post(
        "/api/v1/sources",
        json={
            "source_type": "eightfold",
            "external_identifier": unique("jobs.synthco") + ".example",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["category"] == "company_board"
    assert body["rate_limit_per_minute"] == 30
    assert body["company_name"] == "Synthco"
