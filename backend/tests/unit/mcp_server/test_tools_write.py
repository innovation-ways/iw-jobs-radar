"""The write tools: off unless allowed, versioned, narrow (ADR-078 point 5)."""

from typing import Any

import pytest
from mcp import Client

from jobs_radar.mcp_server.server import build_server
from jobs_radar.mcp_server.untrusted import OPEN

from . import support
from .support import FakeApi, api_error

WRITE_TOOLS = {"inbox_action", "start_collection", "summarise_job"}


def _routes() -> dict[tuple[str, str], Any]:
    return {
        **support.read_routes(),
        ("POST", "/inbox/{job_inbox_item_id}/actions"): {
            "item": support.inbox_item(11, is_shortlisted=True, version=4),
            "event": {
                "inbox_event_id": 2,
                "action": "shortlist",
                "actor": "user",
                "from_state": "unread",
                "to_state": "unread",
                "created_at": "2026-10-02T10:00:00Z",
            },
        },
        ("POST", "/collection-runs"): {**support.run(), "status": "queued"},
        ("POST", "/jobs/{job_posting_id}/summary"): {
            "summary": f"Short summary. {support.HOSTILE}",
            "created": True,
        },
    }


async def raw(
    api: FakeApi, name: str, arguments: dict[str, Any] | None = None, *, writes: bool = True
) -> Any:
    server = build_server(support.settings(writes=writes), api)  # type: ignore[arg-type]
    async with Client(server) as client:
        return await client.call_tool(name, arguments or {})


async def call(api: FakeApi, name: str, arguments: dict[str, Any] | None = None) -> Any:
    result = await raw(api, name, arguments)
    assert not result.is_error, result.content
    return result.structured_content


async def test_write_tools_exist_only_when_allowed() -> None:
    for writes, expected in ((False, set()), (True, WRITE_TOOLS)):
        server = build_server(support.settings(writes=writes), FakeApi())  # type: ignore[arg-type]
        async with Client(server) as client:
            names = {t.name for t in (await client.list_tools()).tools}
        assert names & WRITE_TOOLS == expected


async def test_a_disabled_write_tool_cannot_be_called_and_reaches_no_api() -> None:
    api = FakeApi(_routes())
    result = await raw(
        api,
        "inbox_action",
        {"job_inbox_item_id": 11, "action": "ignore", "expected_version": 3},
        writes=False,
    )
    assert result.is_error
    assert api.calls == []


async def test_write_tools_are_not_read_only_and_never_destructive() -> None:
    server = build_server(support.settings(writes=True), FakeApi())  # type: ignore[arg-type]
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    for name in WRITE_TOOLS:
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.read_only_hint is False
        assert annotations.destructive_hint is False
        assert annotations.open_world_hint is False
    required = tools["inbox_action"].input_schema["required"]
    assert {"job_inbox_item_id", "action", "expected_version"} <= set(required)


async def test_inbox_action_sends_only_what_was_given() -> None:
    api = FakeApi(_routes())
    data = await call(
        api,
        "inbox_action",
        {
            "job_inbox_item_id": 11,
            "action": "shortlist",
            "expected_version": 3,
            "note": "Looks good",
        },
    )
    assert data["item"]["is_shortlisted"] is True
    assert data["item"]["version"] == 4
    assert data["event"]["action"] == "shortlist"
    sent = api.calls[0]
    assert sent["path"] == {"job_inbox_item_id": 11}
    assert sent["json"] == {"action": "shortlist", "expected_version": 3, "note": "Looks good"}


@pytest.mark.parametrize(
    "arguments",
    [
        {"job_inbox_item_id": 11, "action": "delete", "expected_version": 3},
        {"job_inbox_item_id": 11, "action": "ignore"},
        {"job_inbox_item_id": 11, "action": "ignore", "expected_version": 0},
        {"job_inbox_item_id": 0, "action": "ignore", "expected_version": 1},
        {"job_inbox_item_id": 11, "action": "ignore", "expected_version": 1, "note": "n" * 2001},
        {
            "job_inbox_item_id": 11,
            "action": "record_application",
            "expected_version": 1,
            "application_url": "javascript:alert(1)",
        },
    ],
)
async def test_inbox_action_validates_before_calling_the_api(arguments: dict[str, Any]) -> None:
    api = FakeApi(_routes())
    result = await raw(api, "inbox_action", arguments)
    assert result.is_error
    assert api.calls == []


async def test_a_stale_version_tells_the_agent_to_read_again() -> None:
    api = FakeApi(_routes())
    api.routes[("POST", "/inbox/{job_inbox_item_id}/actions")] = api_error(
        "conflict", "The item changed since you read it.", 409
    )
    result = await raw(
        api, "inbox_action", {"job_inbox_item_id": 11, "action": "archive", "expected_version": 1}
    )
    assert result.is_error
    message = result.content[0].text
    assert "conflict" in message and "get_job" in message


async def test_start_collection_queues_a_run() -> None:
    api = FakeApi(_routes())
    data = await call(api, "start_collection")
    assert data["status"] == "queued"
    assert api.calls[0]["method"] == "POST"
    assert api.calls[0]["template"] == "/collection-runs"


async def test_summarise_job_wraps_the_model_text() -> None:
    api = FakeApi(_routes())
    data = await call(api, "summarise_job", {"job_posting_id": 211})
    assert data["created"] is True
    assert data["untrusted_summary"].startswith(OPEN)
    assert api.calls[0]["path"] == {"job_posting_id": 211}


async def test_the_model_being_unavailable_reaches_the_agent() -> None:
    api = FakeApi(_routes())
    api.routes[("POST", "/jobs/{job_posting_id}/summary")] = api_error(
        "dependency_unavailable", "No local model is configured.", 503
    )
    result = await raw(api, "summarise_job", {"job_posting_id": 211})
    assert result.is_error
    assert "No local model" in result.content[0].text
