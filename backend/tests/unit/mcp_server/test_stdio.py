"""The real process over stdio: clean protocol, fail-closed start (ADR-078).

A stub API runs on loopback in a thread; the server is a subprocess, exactly as an agent's client
would start it. Nothing here touches the network beyond 127.0.0.1.
"""

import json
import subprocess  # runs this interpreter on our own module
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from . import support

ANSWERS = {
    "/api/v1/pipeline/status": support.pipeline(),
    "/api/v1/widget/summary": support.widget(),
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps(ANSWERS.get(self.path.split("?")[0], {})).encode()
        self.send_response(200 if self.path.split("?")[0] in ANSWERS else 404)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # silence the test output
        pass


@pytest.fixture
def stub_api() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def _environment(tmp_path: Path, **extra: str) -> dict[str, str]:
    # A minimal environment: no JOBS_RADAR_* from the developer's shell, no real .env file.
    return {
        "PATH": "/usr/bin:/bin",
        "JOBS_RADAR_ENV_FILE": str(tmp_path / "no-such.env"),
        **extra,
    }


async def test_serves_tools_over_stdio(stub_api: str, tmp_path: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "jobs_radar.mcp_server"],
        env=_environment(tmp_path, JOBS_RADAR_MCP_ENABLED="true", JOBS_RADAR_MCP_API_URL=stub_api),
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        assert "list_inbox" in {t.name for t in tools.tools}
        assert "inbox_action" not in {t.name for t in tools.tools}  # writes stay off
        result = await session.call_tool("get_status", {})
        assert not result.is_error
        assert result.structured_content["to_review"] == 4  # type: ignore[index]


def test_does_not_start_when_not_enabled(tmp_path: Path) -> None:
    completed = subprocess.run(  # our own interpreter and module
        [sys.executable, "-m", "jobs_radar.mcp_server"],
        env=_environment(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        input="",
    )
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "JOBS_RADAR_MCP_ENABLED=true" in completed.stderr
