"""The read tools, through an in-process MCP client and a fake API (ADR-078 phase 1)."""

import json
from typing import Any

import pytest
from mcp import Client

from jobs_radar.mcp_server.server import build_server
from jobs_radar.mcp_server.untrusted import CLOSE, OPEN

from . import support
from .support import FakeApi, api_error


@pytest.fixture
def api() -> FakeApi:
    return FakeApi(support.read_routes())


async def raw(api: FakeApi, name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Call a tool on a fresh in-process client (one per call: the SDK's task scopes need it)."""
    server = build_server(support.settings(), api)  # type: ignore[arg-type]
    async with Client(server) as client:
        return await client.call_tool(name, arguments or {})


async def call(api: FakeApi, name: str, arguments: dict[str, Any] | None = None) -> Any:
    result = await raw(api, name, arguments)
    assert not result.is_error, result.content
    return result.structured_content


async def test_get_status_merges_pipeline_and_widget(api: FakeApi) -> None:
    data = await call(api, "get_status", {"fit_min": 70})
    assert data["status"] == "ready"
    assert data["pipeline_state"] == "working"
    assert data["to_review"] == 4
    assert data["best_fit"] == 91
    widget_call = next(c for c in api.calls if c["template"] == "/widget/summary")
    assert widget_call["params"]["fit_min"] == 70


async def test_list_inbox_is_compact_and_passes_filters(api: FakeApi) -> None:
    data = await call(
        api,
        "list_inbox",
        {"state": "to_review", "fit_min": 60, "engagement": ["freelance"], "text": "python"},
    )
    first, second = data["items"]
    assert first["job_inbox_item_id"] == 11
    assert first["version"] == 3
    assert first["company"] == "Example Corp"
    assert first["evaluation"]["fit_score"] == 82
    assert first["sources"] == ["Example Corp"]  # de-duplicated names, no URLs or similarity
    assert second["evaluation"] is None and second["evaluated"] is False
    assert "signals" not in first
    assert data["next_cursor"] == "abc"
    assert data["counts"]["unread"] == 2
    params = api.calls[0]["params"]
    assert params["state"] == "to_review"
    assert params["q"] == "python"
    assert params["engagement"] == ["freelance"]
    assert params["limit"] == 20


@pytest.mark.parametrize(
    "arguments",
    [{"limit": 0}, {"limit": 51}, {"fit_min": 101}, {"state": "everything"}, {"sort": "random"}],
)
async def test_list_inbox_rejects_bad_arguments(api: FakeApi, arguments: dict[str, Any]) -> None:
    result = await raw(api, "list_inbox", arguments)
    assert result.is_error


async def test_get_job_wraps_every_third_party_text(api: FakeApi) -> None:
    data = await call(api, "get_job", {"job_inbox_item_id": 11, "max_chars": 300})
    assert data["summary"]["version"] == 3
    assert data["untrusted_description"].startswith(OPEN)
    assert data["untrusted_description"].endswith(CLOSE)
    assert data["untrusted_ai_summary"].startswith(OPEN)
    evidence = data["dimensions"][0]["untrusted_evidence"]
    assert evidence.startswith(OPEN)
    assert support.HOSTILE in evidence  # kept, but only inside the wrapper
    assert data["dimensions"][0]["explanation"] == "The role family matches."
    assert data["technologies"] == [{"name": "Python", "importance": "required"}]
    assert data["history"][0]["action"] == "open"
    assert api.calls[0]["path"] == {"job_inbox_item_id": 11}


async def test_get_job_limits_the_description(api: FakeApi) -> None:
    api.routes[("GET", "/inbox/{job_inbox_item_id}")] = support.inbox_detail("q" * 9000)
    data = await call(api, "get_job", {"job_inbox_item_id": 11})
    assert data["untrusted_description"].count("q") == 6000
    assert "truncated" in data["untrusted_description"]


async def test_get_job_survives_a_job_without_evaluation(api: FakeApi) -> None:
    detail = support.inbox_detail()
    detail.update(evaluation=None, evaluated=False, dimensions=[])
    detail["brief"] = {"summary": None, "summary_model": None, "technologies": [], "facts": []}
    api.routes[("GET", "/inbox/{job_inbox_item_id}")] = detail
    data = await call(api, "get_job", {"job_inbox_item_id": 11})
    assert data["summary"]["evaluation"] is None
    assert data["untrusted_ai_summary"] is None
    assert data["dimensions"] == []


async def test_digest_uses_compact_rows(api: FakeApi) -> None:
    data = await call(api, "get_daily_digest")
    assert data["new_high_fit"][0]["job_inbox_item_id"] == 11
    assert "signals" not in data["new_high_fit"][0]
    assert data["changed_shortlisted"][0]["changed_fields"] == ["salary"]
    assert data["source_health"][0]["status"] == "failing"


async def test_profile_and_intents_come_back_in_full(api: FakeApi) -> None:
    profile = await call(api, "get_career_profile")
    facts = profile["items"][0]["current_revision"]["facts"]
    assert facts["experience"][0]["employer"] == "Fictional Ltd"
    assert facts["education"][0]["institution"] == "Example University"
    intents = await call(api, "list_search_intents")
    definition = intents["items"][0]["current_revision"]["definition"]
    assert definition["compensation"] == {"annual_min": 70000}


async def test_secret_looking_keys_are_never_returned(api: FakeApi) -> None:
    for name in ("get_career_profile", "get_job"):
        arguments = {"job_inbox_item_id": 11} if name == "get_job" else {}
        text = json.dumps(await call(api, name, arguments))
        assert "decoy-profile-token" not in text
        assert "decoy-evidence-key" not in text
        assert '"internal_token"' not in text


async def test_sources_show_key_state_never_the_key(api: FakeApi) -> None:
    data = await call(api, "list_sources")
    saved, not_needed, missing = data["items"]
    assert (saved["needs_key"], saved["key_saved"]) == (True, True)
    assert (not_needed["needs_key"], not_needed["key_saved"]) == (False, False)
    assert (missing["needs_key"], missing["key_saved"]) == (True, False)
    assert "credential_status" not in saved
    assert "external_identifier" not in saved
    assert saved["last_result"]["outcome"] == "success"


async def test_collection_runs(api: FakeApi) -> None:
    data = await call(api, "list_collection_runs", {"limit": 5})
    assert data["items"][0]["results"][0]["new_count"] == 2
    assert data["next_before_collection_run_id"] == 29
    assert api.calls[0]["params"]["limit"] == 5


async def test_companies_and_dossier(api: FakeApi) -> None:
    listing = await call(api, "list_companies", {"followed_only": True})
    assert listing["total"] == 1
    assert listing["items"][0]["name"] == "Example Corp"
    assert api.calls[0]["params"]["followed_only"] is True
    dossier = await call(api, "get_company", {"company_id": 5})
    assert dossier["facts"][0]["untrusted_value"].startswith(OPEN)
    assert dossier["facts"][0]["source_name"] == "Wikidata"
    assert len(dossier["offers"]) == 20
    assert dossier["offers_truncated"] is True


async def test_trends(api: FakeApi) -> None:
    data = await call(api, "get_trends", {"kind": "skill", "weeks": 8})
    assert data["rows"][0]["label"] == "Python"
    assert api.calls[0]["params"]["weeks"] == 8
    result = await raw(api, "get_trends", {"kind": "mood"})
    assert result.is_error


async def test_api_errors_reach_the_agent_with_code_and_request_id(api: FakeApi) -> None:
    api.routes[("GET", "/inbox/{job_inbox_item_id}")] = api_error()
    result = await raw(api, "get_job", {"job_inbox_item_id": 999})
    assert result.is_error
    message = result.content[0].text  # type: ignore[union-attr]
    assert "not_found" in message and "No such item." in message and "req-9" in message


async def test_unexpected_failures_do_not_leak_internals(api: FakeApi) -> None:
    api.routes[("GET", "/trends")] = RuntimeError("postgresql://user:pw@internal/db")
    result = await raw(api, "get_trends", {"kind": "skill"})
    assert result.is_error
    assert "postgresql" not in result.content[0].text  # type: ignore[union-attr]
