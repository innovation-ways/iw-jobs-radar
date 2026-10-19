"""Entry point: ``python -m jobs_radar.mcp_server`` runs the server over stdio (ADR-078).

Fail closed: unless ``JOBS_RADAR_MCP_ENABLED`` is ``true`` the process says so on stderr and exits
with status 2 before building anything or opening a connection. stdout belongs to the protocol,
so every message and every log line goes to stderr.
"""

import logging
import sys
from collections.abc import Mapping
from pathlib import Path

from jobs_radar.mcp_server.api_client import ApiClient
from jobs_radar.mcp_server.server import build_server
from jobs_radar.mcp_server.settings import load_settings

EXIT_NOT_STARTED = 2

DISABLED_MESSAGE = (
    "Jobs Radar MCP server is disabled: set JOBS_RADAR_MCP_ENABLED=true in .env to enable it."
)


def main(environ: Mapping[str, str] | None = None, env_file: Path | None = None) -> int:
    """Start the server; return the process exit status (not reached while it serves)."""
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    try:
        settings = load_settings(environ) if env_file is None else load_settings(environ, env_file)
    except ValueError as error:
        sys.stderr.write(f"Jobs Radar MCP server: invalid configuration: {error}\n")
        return EXIT_NOT_STARTED
    if not settings.enabled:
        sys.stderr.write(DISABLED_MESSAGE + "\n")
        return EXIT_NOT_STARTED
    api = ApiClient(settings.api_url, timeout=settings.timeout_seconds)
    build_server(settings, api).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
