"""MCP server settings: fail closed, ``.env`` parsed narrowly (ADR-078 points 10 and 7)."""

from pathlib import Path

import pytest

from jobs_radar.mcp_server.settings import McpSettings, load_settings

DECOY_KEY = "decoy-credential-key-do-not-leak"


def _env(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_not_enabled_when_nothing_is_set(tmp_path: Path) -> None:
    settings = load_settings(environ={}, env_file=tmp_path / "missing.env")
    assert settings.enabled is False
    assert settings.allow_writes is False


@pytest.mark.parametrize("value", ["false", "0", "no", "", "yes", "TRUE1", "enabled", "2"])
def test_only_true_enables(tmp_path: Path, value: str) -> None:
    env = _env(tmp_path, f"JOBS_RADAR_MCP_ENABLED={value}\n")
    assert load_settings(environ={}, env_file=env).enabled is False


@pytest.mark.parametrize("value", ["true", "TRUE", "True", " true "])
def test_true_enables(tmp_path: Path, value: str) -> None:
    env = _env(tmp_path, f"JOBS_RADAR_MCP_ENABLED={value}\n")
    assert load_settings(environ={}, env_file=env).enabled is True


def test_writes_need_their_own_switch(tmp_path: Path) -> None:
    env = _env(tmp_path, "JOBS_RADAR_MCP_ENABLED=true\n")
    settings = load_settings(environ={}, env_file=env)
    assert settings.enabled is True
    assert settings.allow_writes is False


def test_writes_alone_do_not_enable(tmp_path: Path) -> None:
    env = _env(tmp_path, "JOBS_RADAR_MCP_ALLOW_WRITES=true\n")
    settings = load_settings(environ={}, env_file=env)
    assert settings.enabled is False
    # The write flag is meaningless without the master switch.
    assert settings.allow_writes is False


def test_process_environment_beats_the_file(tmp_path: Path) -> None:
    env = _env(tmp_path, "JOBS_RADAR_MCP_ENABLED=false\nJOBS_RADAR_API_PORT=8100\n")
    settings = load_settings(
        environ={"JOBS_RADAR_MCP_ENABLED": "true", "JOBS_RADAR_API_PORT": "8101"}, env_file=env
    )
    assert settings.enabled is True
    assert settings.api_url == "http://127.0.0.1:8101"


def test_default_api_url_follows_the_api_port(tmp_path: Path) -> None:
    assert load_settings(environ={}, env_file=tmp_path / "x").api_url == "http://127.0.0.1:8100"
    env = _env(tmp_path, "JOBS_RADAR_API_PORT=9000\n")
    assert load_settings(environ={}, env_file=env).api_url == "http://127.0.0.1:9000"


def test_explicit_api_url_wins_and_loses_trailing_slash(tmp_path: Path) -> None:
    env = _env(tmp_path, "JOBS_RADAR_MCP_API_URL=http://192.0.2.10:8100/\n")
    assert load_settings(environ={}, env_file=env).api_url == "http://192.0.2.10:8100"


@pytest.mark.parametrize("url", ["ftp://host", "javascript:alert(1)", "not a url", "http://"])
def test_bad_api_url_is_rejected(tmp_path: Path, url: str) -> None:
    env = _env(tmp_path, f"JOBS_RADAR_MCP_API_URL={url}\n")
    with pytest.raises(ValueError, match="JOBS_RADAR_MCP_API_URL"):
        load_settings(environ={}, env_file=env)


def test_bad_port_is_rejected(tmp_path: Path) -> None:
    env = _env(tmp_path, "JOBS_RADAR_API_PORT=abc\n")
    with pytest.raises(ValueError, match="JOBS_RADAR_API_PORT"):
        load_settings(environ={}, env_file=env)


def test_timeout_default_and_bounds(tmp_path: Path) -> None:
    assert load_settings(environ={}, env_file=tmp_path / "x").timeout_seconds == 15.0
    env = _env(tmp_path, "JOBS_RADAR_MCP_TIMEOUT_SECONDS=5\n")
    assert load_settings(environ={}, env_file=env).timeout_seconds == 5.0
    for bad in ("0", "-1", "500", "abc"):
        env = _env(tmp_path, f"JOBS_RADAR_MCP_TIMEOUT_SECONDS={bad}\n")
        with pytest.raises(ValueError, match="JOBS_RADAR_MCP_TIMEOUT_SECONDS"):
            load_settings(environ={}, env_file=env)


def test_dotenv_syntax_is_handled(tmp_path: Path) -> None:
    env = _env(
        tmp_path,
        "# a comment\n"
        "\n"
        "export JOBS_RADAR_MCP_ENABLED=true   # trailing comment\n"
        'JOBS_RADAR_API_PORT="8102"\n'
        "JOBS_RADAR_MCP_TIMEOUT_SECONDS='7'\n"
        "no equals sign here\n",
    )
    settings = load_settings(environ={}, env_file=env)
    assert settings.enabled is True
    assert settings.api_url == "http://127.0.0.1:8102"
    assert settings.timeout_seconds == 7.0


def test_other_keys_are_never_held(tmp_path: Path) -> None:
    env = _env(
        tmp_path,
        f"JOBS_RADAR_CREDENTIAL_KEY={DECOY_KEY}\n"
        f"JOBS_RADAR_DB_PASSWORD={DECOY_KEY}\n"
        "JOBS_RADAR_MCP_ENABLED=true\n",
    )
    settings = load_settings(environ={}, env_file=env)
    assert DECOY_KEY not in repr(settings)
    assert DECOY_KEY not in repr(settings.__dict__)
    assert not hasattr(settings, "credential_key")


def test_environment_is_filtered_too() -> None:
    settings = load_settings(
        environ={"JOBS_RADAR_CREDENTIAL_KEY": DECOY_KEY, "JOBS_RADAR_MCP_ENABLED": "true"},
        env_file=None,
    )
    assert DECOY_KEY not in repr(settings.__dict__)


def test_unreadable_env_file_means_not_enabled(tmp_path: Path) -> None:
    # A directory where the file should be: reading fails, and the server must stay off.
    settings = load_settings(environ={}, env_file=tmp_path)
    assert settings.enabled is False


def test_env_file_comes_from_jobs_radar_env_file(tmp_path: Path) -> None:
    env = _env(tmp_path, "JOBS_RADAR_MCP_ENABLED=true\n")
    settings = load_settings(environ={"JOBS_RADAR_ENV_FILE": str(env)})
    assert settings.enabled is True


def test_settings_are_frozen() -> None:
    settings = McpSettings()
    with pytest.raises(AttributeError):
        settings.enabled = True  # type: ignore[misc]


def test_url_with_credentials_is_rejected_without_echoing_them(tmp_path: Path) -> None:
    env = _env(tmp_path, "JOBS_RADAR_MCP_API_URL=http://user:hunter2@192.0.2.10:8100\n")
    with pytest.raises(ValueError, match="JOBS_RADAR_MCP_API_URL") as error:
        load_settings(environ={}, env_file=env)
    assert "hunter2" not in str(error.value)
