"""The launcher's help, URLs and colour behaviour (no Docker is touched)."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "jobs-radar.sh"
ESC = "\x1b["


def launcher(
    *args: str, env_file: str | None = None, **env: str
) -> subprocess.CompletedProcess[str]:
    base = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("JOBS_RADAR_") and k not in {"NO_COLOR", "FORCE_COLOR"}
    }
    base["JOBS_RADAR_ENV_FILE"] = env_file or "/nonexistent/.env"
    return subprocess.run(  # noqa: S603  # fixed local script
        [str(SCRIPT), *args],
        cwd=ROOT,
        env={**base, **env},
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )


def test_the_script_is_valid_bash() -> None:
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0  # noqa: S603, S607


@pytest.mark.parametrize(
    "flag",
    [
        "--init-env",
        "--quick-start",
        "--quick-stop",
        "--start",
        "--stop",
        "--restart",
        "--rebuild",
        "--status",
        "--health",
        "--wait-healthy",
        "--logs",
        "--urls",
        "--db-migrate",
        "--psql",
        "--backup",
        "--restore-drill",
        "--frontend-start",
        "--frontend-stop",
        "--frontend-clean",
        "--tests",
        "--demo",
        "--demo-stop",
        "--mcp",
        "--nuclear-reset",
        "--help",
    ],
)
def test_help_documents_every_flag(flag: str) -> None:
    result = launcher("--help")
    assert result.returncode == 0
    assert flag in result.stdout


def test_an_unknown_option_fails_and_shows_the_help() -> None:
    result = launcher("--nonsense")
    assert result.returncode == 1
    assert "Unknown option" in result.stderr
    assert "Usage" in result.stdout


def test_urls_use_the_configured_ports() -> None:
    result = launcher("--urls", JOBS_RADAR_API_PORT="9111", JOBS_RADAR_FRONTEND_PORT="9222")
    assert result.returncode == 0
    assert "http://127.0.0.1:9222" in result.stdout
    assert "http://127.0.0.1:9111/docs" in result.stdout
    assert "9111/healthz" in result.stdout


def test_urls_show_network_addresses_when_exposed(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "JOBS_RADAR_API_BIND=0.0.0.0\nJOBS_RADAR_DB_BIND=0.0.0.0\nJOBS_RADAR_DB_PORT=5999\n"
    )
    out = launcher("--urls", env_file=str(env_file)).stdout
    assert "network" in out.lower()
    assert "5999" in out


def test_urls_say_loopback_only_when_not_exposed() -> None:
    assert "this machine only" in launcher("--urls").stdout.lower()


def test_no_colour_codes_when_not_a_terminal_or_no_color() -> None:
    assert ESC not in launcher("--help").stdout
    assert ESC not in launcher("--help", NO_COLOR="1", FORCE_COLOR="1").stdout


def test_colour_is_used_when_forced() -> None:
    assert ESC in launcher("--help", FORCE_COLOR="1").stdout
    assert ESC in launcher("--urls", FORCE_COLOR="1").stdout


def test_logs_needs_a_service() -> None:
    result = launcher("--logs")
    assert result.returncode == 1
    assert "needs a service" in result.stderr


def test_demo_uses_its_own_database_and_ports() -> None:
    """The demo must never share the real database or the real ports (README: demo section)."""
    text = SCRIPT.read_text()
    assert "JOBS_RADAR_DB_NAME=jobs_radar_demo" in text
    assert "JOBS_RADAR_API_PORT=8101" in text
    assert "JOBS_RADAR_FRONTEND_PORT=5181" in text
    # The idle worker is the only worker allowed against the demo database.
    assert "jobs_radar.demo.idle_worker" in text


def test_demo_stop_is_harmless_when_nothing_runs() -> None:
    result = launcher("--demo-stop")
    assert result.returncode == 0


def test_a_trailing_comment_leaves_no_spaces_in_the_value(tmp_path: Path) -> None:
    """`.env.example` has `KEY=value   # comment`; the value must reach the app without spaces."""
    env_file = tmp_path / ".env"
    env_file.write_text("JOBS_RADAR_API_PORT=9333      # the API port\n")
    result = launcher("--urls", env_file=str(env_file))
    assert "http://127.0.0.1:9333/docs" in result.stdout


def test_mcp_says_it_is_off_and_how_to_turn_it_on() -> None:
    result = launcher("--mcp")
    assert result.returncode == 0
    assert "off" in result.stdout.lower()
    assert "JOBS_RADAR_MCP_ENABLED=true" in result.stdout
    assert "claude mcp add" not in result.stdout  # nothing to connect while it is off


def test_mcp_shows_the_state_and_the_connection_commands(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "JOBS_RADAR_MCP_ENABLED=true\nJOBS_RADAR_DB_PASSWORD=decoy-password-123\n"
        "JOBS_RADAR_CREDENTIAL_KEY=decoy-key-456\n"
    )
    result = launcher("--mcp", env_file=str(env))
    assert result.returncode == 0
    assert "read-only" in result.stdout.lower()
    assert "write tools are on" not in result.stdout.lower()
    assert "jobs_radar.mcp_server" in result.stdout
    assert "claude mcp add" in result.stdout
    assert str(ROOT) in result.stdout  # the real path of this checkout, not a placeholder
    assert "decoy-password-123" not in result.stdout + result.stderr
    assert "decoy-key-456" not in result.stdout + result.stderr


def test_mcp_reports_writes_only_with_both_switches(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("JOBS_RADAR_MCP_ALLOW_WRITES=true\n")
    # The write switch means nothing without the master switch.
    assert "write tools are on" not in launcher("--mcp", env_file=str(env)).stdout.lower()
    env.write_text("JOBS_RADAR_MCP_ENABLED=true\nJOBS_RADAR_MCP_ALLOW_WRITES=true\n")
    result = launcher("--mcp", env_file=str(env))
    assert "write tools are on" in result.stdout.lower()
