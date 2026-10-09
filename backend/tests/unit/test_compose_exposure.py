"""Docker Compose publishes ports on loopback unless the owner chooses otherwise (ADR-009, T8.2)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_every_published_port_defaults_to_loopback() -> None:
    lines = [
        line.strip()
        for line in (ROOT / "docker-compose.yml").read_text().splitlines()
        if re.match(r'^\s*-\s*"\$\{|^\s*-\s*"\d', line)
    ]
    assert lines, "expected published ports"
    for line in lines:
        assert re.search(r'"\$\{JOBS_RADAR_(API|DB)_BIND:-127\.0\.0\.1\}:', line), line


def test_the_example_environment_is_loopback_and_has_no_secret_values() -> None:
    example = (ROOT / ".env.example").read_text()
    for name in ("JOBS_RADAR_API_BIND", "JOBS_RADAR_DB_BIND"):
        match = re.search(rf"^{name}=(.*)$", example, re.M)
        assert match is None or match.group(1) in {"127.0.0.1", ""}, name
    for name in ("JOBS_RADAR_DB_PASSWORD", "JOBS_RADAR_CREDENTIAL_KEY"):
        assert re.search(rf"^{name}=\s*(#.*)?$", example, re.M), (
            f"{name} must be empty in .env.example"
        )


def test_secrets_and_backups_are_git_ignored() -> None:
    ignore = (ROOT / ".gitignore").read_text()
    assert re.search(r"^\.env$", ignore, re.M) and re.search(r"^/backups/$", ignore, re.M)
