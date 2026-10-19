"""Opt-in smoke test of the MCP server against a RUNNING API (ADR-078). Never in the default run.

Start the fictional demo first (``make demo``: API on 8101, invented data) and run ``make smoke``.
Set ``JOBS_RADAR_SMOKE_MCP_API_URL`` to use another API; do not point it at your real data if you
send what the tools return to a cloud model.
"""

import os
import sys

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.skipif(
    os.environ.get("JOBS_RADAR_SMOKE") != "1",
    reason="opt-in: run `make smoke` (needs a running API, for example `make demo`)",
)

API_URL = os.environ.get("JOBS_RADAR_SMOKE_MCP_API_URL", "http://127.0.0.1:8101")


async def test_the_stdio_server_answers_from_a_running_api() -> None:
    try:
        httpx.get(f"{API_URL}/healthz", timeout=3).raise_for_status()
    except httpx.HTTPError:
        pytest.skip(f"no API at {API_URL}: start the demo with `make demo`")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "jobs_radar.mcp_server"],
        env={
            "PATH": os.environ.get("PATH", ""),
            "JOBS_RADAR_MCP_ENABLED": "true",
            "JOBS_RADAR_MCP_API_URL": API_URL,
            "JOBS_RADAR_ENV_FILE": "/nonexistent",
        },
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        status = await session.call_tool("get_status", {})
        assert not status.is_error
        inbox = await session.call_tool("list_inbox", {"limit": 3})
        assert not inbox.is_error
        assert "counts" in (inbox.structured_content or {})
