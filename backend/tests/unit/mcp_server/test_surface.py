"""The tool surface is a contract: a snapshot, plus rules every tool must obey (ADR-078)."""

import json
from pathlib import Path
from typing import Any

from mcp import Client

from jobs_radar.mcp_server.api_client import ALLOWED_ROUTES, READ_ROUTES, WRITE_ROUTES
from jobs_radar.mcp_server.server import build_server

from . import support
from .support import FakeApi

READ_TOOLS = {
    "get_status",
    "list_inbox",
    "get_job",
    "get_daily_digest",
    "get_career_profile",
    "list_search_intents",
    "list_sources",
    "list_collection_runs",
    "list_companies",
    "get_company",
    "get_trends",
}
WRITE_TOOLS = {"inbox_action", "start_collection", "summarise_job"}
FORBIDDEN_PARAMETERS = {"id", "url", "path", "uri", "credential", "token", "password", "api_key"}
OPENAPI = Path(__file__).resolve().parents[3] / "openapi.json"


async def list_tools(*, writes: bool) -> list[Any]:
    server = build_server(support.settings(writes=writes), FakeApi())  # type: ignore[arg-type]
    async with Client(server) as client:
        return (await client.list_tools()).tools


async def test_read_only_surface_is_exactly_the_documented_tools() -> None:
    tools = await list_tools(writes=False)
    assert {t.name for t in tools} == READ_TOOLS


async def test_every_read_tool_is_annotated_read_only_and_closed_world() -> None:
    for tool in await list_tools(writes=False):
        assert tool.annotations is not None, tool.name
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.destructive_hint is False, tool.name
        assert tool.annotations.open_world_hint is False, tool.name


async def test_every_tool_has_a_description_and_typed_output() -> None:
    for tool in await list_tools(writes=False):
        assert tool.description and len(tool.description.split()) >= 4, tool.name
        assert tool.output_schema is not None, tool.name


async def test_tools_that_return_third_party_text_say_so() -> None:
    by_name = {t.name: t for t in await list_tools(writes=False)}
    for name in ("get_job", "get_company"):
        assert "untrusted_" in by_name[name].description


async def test_no_tool_takes_a_url_path_secret_or_bare_id() -> None:
    for tool in await list_tools(writes=False):
        names = set(tool.input_schema.get("properties", {}))
        assert not names & FORBIDDEN_PARAMETERS, (tool.name, names & FORBIDDEN_PARAMETERS)


async def test_write_surface_is_exactly_the_documented_tools_and_obeys_the_same_rules() -> None:
    tools = await list_tools(writes=True)
    assert {t.name for t in tools} == READ_TOOLS | WRITE_TOOLS
    for tool in tools:
        names = set(tool.input_schema.get("properties", {}))
        assert not names & FORBIDDEN_PARAMETERS, tool.name
        assert tool.annotations is not None and tool.annotations.destructive_hint is False


async def test_server_instructions_warn_about_untrusted_text() -> None:
    server = build_server(support.settings(), FakeApi())  # type: ignore[arg-type]
    async with Client(server) as client:
        text = client.instructions or ""
    assert "untrusted_" in text and "never as instructions" in text


async def test_outputs_never_contain_secret_looking_keys() -> None:
    forbidden = ("credential", "secret", "api_key", "token", "password")
    server = build_server(support.settings(), FakeApi(support.read_routes()))  # type: ignore[arg-type]
    arguments: dict[str, dict[str, Any]] = {
        "get_job": {"job_inbox_item_id": 11},
        "get_company": {"company_id": 5},
        "get_trends": {"kind": "skill"},
    }
    async with Client(server) as client:
        for name in READ_TOOLS:
            result = await client.call_tool(name, arguments.get(name, {}))
            assert not result.is_error, (name, result.content)
            keys: list[str] = []

            def walk(value: Any, keys: list[str] = keys) -> None:
                if isinstance(value, dict):
                    keys.extend(value)
                    for item in value.values():
                        walk(item)
                elif isinstance(value, list):
                    for item in value:
                        walk(item)

            walk(result.structured_content)
            bad = [k for k in keys if any(word in k.lower() for word in forbidden)]
            assert not bad, (name, bad)


def test_allow_list_matches_the_openapi_description() -> None:
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))["paths"]
    for method, template in sorted(ALLOWED_ROUTES):
        operations = spec.get(f"/api/v1{template}")
        assert operations is not None, f"{template} is not in openapi.json"
        assert method.lower() in operations, f"{method} {template} is not in openapi.json"


def test_read_and_write_routes_do_not_overlap_and_writes_are_posts() -> None:
    assert not READ_ROUTES & WRITE_ROUTES
    assert {m for m, _ in READ_ROUTES} == {"GET"}
    assert {m for m, _ in WRITE_ROUTES} == {"POST"}


async def test_read_tools_only_ever_issue_get_requests() -> None:
    api = FakeApi(support.read_routes())
    server = build_server(support.settings(), api)  # type: ignore[arg-type]
    arguments = {"get_job": {"job_inbox_item_id": 11}, "get_company": {"company_id": 5}}
    async with Client(server) as client:
        for name in sorted(READ_TOOLS):
            await client.call_tool(
                name, arguments.get(name, {"kind": "skill"} if name == "get_trends" else {})
            )
    assert api.calls
    assert {call["method"] for call in api.calls} == {"GET"}
