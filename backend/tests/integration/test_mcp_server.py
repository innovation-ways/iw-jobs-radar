"""The MCP server over the real application and a PostgreSQL container (ADR-078).

The MCP tools call the API through an ASGI transport (no socket), so these tests prove the views
fit the real response shapes and that a write goes through the same service rules as the UI.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from mcp import Client
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.factories import unique
from tests.fake_adapter import FakeAdapter, listing, make_posting
from tests.inbox_scene import scene

from jobs_radar.db.models import InboxEvent, SourceConfiguration
from jobs_radar.domain.enums import SourceType
from jobs_radar.mcp_server.api_client import ApiClient
from jobs_radar.mcp_server.server import build_server
from jobs_radar.mcp_server.settings import McpSettings
from jobs_radar.mcp_server.untrusted import CLOSE, OPEN
from jobs_radar.services.collection import CollectionService

pytestmark = pytest.mark.integration


@asynccontextmanager
async def agent(app: FastAPI, *, writes: bool = False) -> AsyncIterator[Client]:
    """An in-process MCP client whose server talks to the real app."""
    api = ApiClient("http://test", timeout=10.0, transport=httpx.ASGITransport(app=app))
    server = build_server(McpSettings(enabled=True, allow_writes=writes), api)
    async with Client(server) as client:
        yield client


async def structured(client: Client, name: str, arguments: dict[str, Any] | None = None) -> Any:
    result = await client.call_tool(name, arguments or {})
    assert not result.is_error, result.content
    return result.structured_content


async def test_list_inbox_matches_the_api_order_and_fields(
    app: FastAPI,
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        s = await scene(session)
        s.session = session
        low = await s.entry(fit=40)
        high = await s.entry(fit=90)
        await session.commit()
    pin = {"search_intent_id": s.intent.search_intent_id, "limit": 50}
    api_ids = [
        i["job_inbox_item_id"]
        for i in (await client.get("/api/v1/inbox", params=pin)).json()["items"]
    ]
    async with agent(app) as mcp:
        data = await structured(mcp, "list_inbox", pin)
    mcp_ids = [i["job_inbox_item_id"] for i in data["items"]]
    assert mcp_ids == api_ids
    assert mcp_ids.index(high.item.job_inbox_item_id) < mcp_ids.index(low.item.job_inbox_item_id)
    row = next(i for i in data["items"] if i["job_inbox_item_id"] == high.item.job_inbox_item_id)
    assert row["evaluation"]["fit_score"] == 90
    assert row["version"] == high.item.version


async def test_get_job_returns_the_stored_evaluation_and_wrapped_text(
    app: FastAPI,
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        s = await scene(session)
        s.session = session
        entry = await s.entry(fit=77)
        await session.commit()
    item_id = entry.item.job_inbox_item_id
    pin = {"search_intent_id": s.intent.search_intent_id}
    api_detail = (await client.get(f"/api/v1/inbox/{item_id}", params=pin)).json()
    async with agent(app) as mcp:
        job = await structured(mcp, "get_job", {"job_inbox_item_id": item_id, **pin})
    assert job["summary"]["evaluation"]["fit_score"] == 77
    assert len(job["dimensions"]) == len(api_detail["dimensions"])
    assert job["untrusted_description"].startswith(OPEN)
    assert job["untrusted_description"].endswith(CLOSE)
    assert api_detail["description_text"] in job["untrusted_description"]


async def test_every_read_tool_works_against_the_real_api(app: FastAPI) -> None:
    arguments = {"get_trends": {"kind": "skill"}}
    async with agent(app) as mcp:
        tools = [t.name for t in (await mcp.list_tools()).tools]
        for name in tools:
            if name in {"get_job", "get_company"}:
                continue  # need an ID: covered by their own tests
            result = await mcp.call_tool(name, arguments.get(name, {}))
            # A fresh database may have no profile or intent; the tool must then say so cleanly.
            if result.is_error:
                assert result.content[0].text.startswith("Error executing tool"), name  # type: ignore[union-attr]
                assert "Traceback" not in result.content[0].text, name  # type: ignore[union-attr]


async def test_inbox_action_follows_the_same_rules_as_the_ui(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        s = await scene(session)
        s.session = session
        entry = await s.entry(fit=80)
        await session.commit()
    item_id = entry.item.job_inbox_item_id
    pin = {"search_intent_id": s.intent.search_intent_id}

    async def events() -> int:
        async with session_factory() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(InboxEvent)
                    .where(InboxEvent.job_inbox_item_id == item_id)
                )
                or 0
            )

    before = await events()
    async with agent(app, writes=True) as mcp:
        stale = await mcp.call_tool(
            "inbox_action",
            {"job_inbox_item_id": item_id, "action": "shortlist", "expected_version": 999, **pin},
        )
        assert stale.is_error
        assert "conflict" in stale.content[0].text  # type: ignore[union-attr]
        assert await events() == before  # nothing changed

        job = await structured(mcp, "get_job", {"job_inbox_item_id": item_id, **pin})
        done = await structured(
            mcp,
            "inbox_action",
            {
                "job_inbox_item_id": item_id,
                "action": "shortlist",
                "expected_version": job["summary"]["version"],
                **pin,
            },
        )
        assert done["item"]["is_shortlisted"] is True
        assert done["item"]["version"] > job["summary"]["version"]
        assert await events() == before + 1


async def test_start_collection_queues_a_run_the_worker_will_execute(
    app: FastAPI,
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A scripted adapter and no other enabled source: the run is executed here, as the worker
    # would, so nothing queued is left behind for the tests that follow.
    async with session_factory() as session:
        await session.execute(update(SourceConfiguration).values(enabled=False))
        await session.commit()
    adapter = FakeAdapter([listing(make_posting("1"))])
    monkeypatch.setattr(app.state, "adapters", {SourceType.GREENHOUSE: adapter})
    added = await client.post(
        "/api/v1/sources",
        json={"source_type": "greenhouse", "external_identifier": unique("mcpboard")},
    )
    assert added.status_code == 201, added.text
    source_id = added.json()["source_configuration_id"]
    try:
        async with agent(app, writes=True) as mcp:
            run = await structured(mcp, "start_collection")
            assert run["status"] == "queued"
            await CollectionService(app.state.session_factory, app.state.adapters).run_queued()
            runs = await structured(mcp, "list_collection_runs", {"limit": 5})
        done = next(r for r in runs["items"] if r["collection_run_id"] == run["collection_run_id"])
        assert done["status"] == "succeeded"
        assert done["sources"]["new"] == 1
    finally:
        async with session_factory() as session:
            await session.execute(
                update(SourceConfiguration)
                .where(SourceConfiguration.source_configuration_id == source_id)
                .values(enabled=False)
            )
            await session.commit()


async def test_a_read_only_server_has_no_way_to_write(app: FastAPI) -> None:
    async with agent(app) as mcp:
        names = {t.name for t in (await mcp.list_tools()).tools}
        assert "inbox_action" not in names
        result = await mcp.call_tool(
            "inbox_action", {"job_inbox_item_id": 1, "action": "ignore", "expected_version": 1}
        )
        assert result.is_error
