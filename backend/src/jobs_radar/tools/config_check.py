"""Check the configuration for exposure and secret-handling mistakes (T8.2, document 08).

Reads the ``JOBS_RADAR_*`` settings (from ``.env`` and the environment) and reports each finding as
``ok``, ``info``, ``warn`` or ``fail``. It changes nothing and prints no secret. The exit code is 1
only for a ``fail``: a world-readable ``.env``, a malformed credential key, a wildcard origin or
host, or (outside development) a short database password. Exposing the API or the database beyond
loopback is a ``warn``: it is a legitimate LAN choice (ADR-009) but must be a conscious one.

Run: ``python -m jobs_radar.tools.config_check`` (``make config-check``).
"""

import ipaddress
import json
import os
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet

PREFIX = "JOBS_RADAR_"


@dataclass(frozen=True)
class Finding:
    """One result of the check."""

    code: str
    level: str  # ok | info | warn | fail
    message: str


def _loopback(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return value == "localhost"


def check(env: Mapping[str, str], *, env_file_mode: int | None) -> list[Finding]:
    """Return the findings for the given settings and the permission bits of ``.env``."""

    def get(name: str, default: str = "") -> str:
        return env.get(PREFIX + name, default)

    found: list[Finding] = []
    if env_file_mode is not None:
        private = not env_file_mode & (stat.S_IRWXG | stat.S_IRWXO)
        found.append(
            Finding(
                "env_file",
                "ok" if private else "fail",
                ".env is private (mode 600)."
                if private
                else ".env is readable by others: run chmod 600 .env (it holds secrets).",
            )
        )

    key = get("CREDENTIAL_KEY")
    if not key:
        found.append(
            Finding(
                "credential_key", "warn", "No credential key: API keys and tokens cannot be stored."
            )
        )
    else:
        try:
            Fernet(key.encode())
            found.append(
                Finding(
                    "credential_key", "ok", "The credential key is valid (back it up separately)."
                )
            )
        except ValueError:
            found.append(
                Finding("credential_key", "fail", "The credential key is not a valid Fernet key.")
            )

    for code, name, what in (
        ("api_bind", "API_BIND", "The API"),
        ("db_bind", "DB_BIND", "The database"),
    ):
        bind = get(name, "127.0.0.1")
        if _loopback(bind):
            found.append(Finding(code, "ok", f"{what} listens on loopback only."))
        else:
            extra = (
                " It has no authentication in V1: use a trusted network only."
                if code == "api_bind"
                else " Only containers need it; prefer 127.0.0.1."
            )
            found.append(
                Finding(code, "warn", f"{what} is reachable from the network ({bind}).{extra}")
            )

    try:
        origins = json.loads(get("CORS_ORIGINS", "[]") or "[]")
    except ValueError:
        origins = []
    found.append(
        Finding("cors", "fail", "CORS allows every origin (*).")
        if "*" in origins
        else Finding("cors", "ok", "CORS lists explicit origins.")
    )
    hosts = {h.strip() for h in get("FRONTEND_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")}
    found.append(
        Finding("allowed_hosts", "fail", "The frontend host check is disabled (wildcard).")
        if hosts & {"*", "all", "true"}
        else Finding("allowed_hosts", "ok", "The frontend accepts explicit hosts only.")
    )

    minimum = 16
    if get("ENV", "dev") != "dev" and len(get("DB_PASSWORD")) < minimum:
        found.append(
            Finding(
                "db_password",
                "fail",
                f"The database password is shorter than {minimum} characters.",
            )
        )
    if get("ALLOW_LOCAL_PROVIDERS").lower() in {"1", "true", "yes"}:
        found.append(
            Finding(
                "local_providers",
                "info",
                "Local model servers are allowed (the configured Ollama host only).",
            )
        )
    return found


def main() -> int:
    """Entry point: print the findings; exit 1 when any is a failure."""
    env_path = Path(__file__).resolve().parents[4] / ".env"
    env: dict[str, str] = {}
    mode: int | None = None
    if env_path.is_file():
        mode = stat.S_IMODE(env_path.stat().st_mode)
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "=" in line:
                name, _, value = line.partition("=")
                env[name.strip()] = value.strip()
    env.update({k: v for k, v in os.environ.items() if k.startswith(PREFIX)})
    findings = check(env, env_file_mode=mode)
    marks = {"ok": "ok  ", "info": "info", "warn": "WARN", "fail": "FAIL"}
    for item in findings:
        print(f"[{marks[item.level]}] {item.message}")
    return 1 if any(f.level == "fail" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
