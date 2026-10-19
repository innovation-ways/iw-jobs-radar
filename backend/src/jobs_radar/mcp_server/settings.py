"""Settings of the MCP server: a master switch that fails closed (ADR-078 point 10).

The process environment wins over the ``.env`` file. From the file only the keys that start with
``JOBS_RADAR_MCP_`` and ``JOBS_RADAR_API_PORT`` are kept, so the encryption key and the database
password are never parsed into memory, logged or passed on. This module deliberately does not use
``jobs_radar.core.settings`` (which requires those secrets).
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_API_PORT = 8100
DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_TIMEOUT_SECONDS = 120.0

_PREFIX = "JOBS_RADAR_MCP_"
_PORT_KEY = "JOBS_RADAR_API_PORT"
_ENV_FILE_KEY = "JOBS_RADAR_ENV_FILE"
# Repository root: .../backend/src/jobs_radar/mcp_server/settings.py -> four levels up.
_DEFAULT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class _Unset:
    """Marker type: use the default ``.env`` location."""


_UNSET = _Unset()


@dataclass(frozen=True)
class McpSettings:
    """What the server needs to know; ``enabled`` is the master switch (default off)."""

    enabled: bool = False
    allow_writes: bool = False
    api_url: str = f"http://127.0.0.1:{DEFAULT_API_PORT}"
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


def _wanted(key: str) -> bool:
    return key.startswith(_PREFIX) or key == _PORT_KEY


def _unquote(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    # An unquoted value ends at a whitespace-preceded ``#`` (inline comment).
    for index, char in enumerate(value):
        if char == "#" and index > 0 and value[index - 1].isspace():
            return value[:index].strip()
    return value


def _read_env_file(path: Path | None) -> dict[str, str]:
    """Parse only the wanted keys of a dotenv file; an unreadable file yields nothing."""
    if path is None:
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    found: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        stripped = stripped.removeprefix("export ").lstrip()
        key, separator, raw = stripped.partition("=")
        key = key.strip()
        if separator and _wanted(key):
            found[key] = _unquote(raw)
    return found


def _as_bool(value: str | None) -> bool:
    """Only the word ``true`` (any case) counts; anything else is off."""
    return value is not None and value.strip().lower() == "true"


def _api_url(values: Mapping[str, str]) -> str:
    explicit = values.get(f"{_PREFIX}API_URL", "").strip()
    if not explicit:
        raw_port = values.get(_PORT_KEY, "").strip()
        if not raw_port:
            return f"http://127.0.0.1:{DEFAULT_API_PORT}"
        try:
            port = int(raw_port)
        except ValueError:
            port = 0
        if not 1 <= port <= 65535:
            msg = f"{_PORT_KEY} must be a port number"
            raise ValueError(msg)
        return f"http://127.0.0.1:{port}"
    parts = urlsplit(explicit)
    valid = parts.scheme in {"http", "https"} and bool(parts.hostname)
    if not valid or parts.username or parts.password:
        # The value is not echoed: a URL can carry credentials.
        msg = f"{_PREFIX}API_URL must be an http(s) URL without credentials"
        raise ValueError(msg)
    return explicit.rstrip("/")


def _timeout(values: Mapping[str, str]) -> float:
    raw = values.get(f"{_PREFIX}TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        seconds = float(raw)
    except ValueError:
        seconds = 0.0
    if not 0 < seconds <= MAX_TIMEOUT_SECONDS:
        msg = f"{_PREFIX}TIMEOUT_SECONDS must be between 0 and {MAX_TIMEOUT_SECONDS:g}"
        raise ValueError(msg)
    return seconds


def load_settings(
    environ: Mapping[str, str] | None = None,
    env_file: _Unset | Path | None = _UNSET,
) -> McpSettings:
    """Build the settings from the process environment and the ``.env`` file.

    Args:
        environ: the process environment (default ``os.environ``).
        env_file: the dotenv file; ``None`` means no file; by default ``JOBS_RADAR_ENV_FILE`` or
            the repository's ``.env``.

    Raises:
        ValueError: a present value is malformed (the message names the variable, never the value).
    """
    env = os.environ if environ is None else environ
    if isinstance(env_file, _Unset):
        configured = env.get(_ENV_FILE_KEY, "").strip()
        env_file = Path(configured) if configured else _DEFAULT_ENV_FILE
    # The file first, then the process environment on top: the environment wins.
    values = _read_env_file(env_file)
    values.update({key: value for key, value in env.items() if _wanted(key)})
    enabled = _as_bool(values.get(f"{_PREFIX}ENABLED"))
    return McpSettings(
        enabled=enabled,
        # The write switch means nothing unless the master switch is on.
        allow_writes=enabled and _as_bool(values.get(f"{_PREFIX}ALLOW_WRITES")),
        api_url=_api_url(values),
        timeout_seconds=_timeout(values),
    )
