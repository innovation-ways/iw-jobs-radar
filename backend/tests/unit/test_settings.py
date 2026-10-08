"""Unit tests for application settings (ADR-032)."""

import pytest
from pydantic import ValidationError

from jobs_radar.core.settings import Settings


def make(**overrides: object) -> Settings:
    """Build settings from explicit values only, ignoring the process environment and any .env file."""
    values: dict[str, object] = {"db_password": "pw"}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_defaults_match_adr_019_and_adr_032() -> None:
    settings = make()
    assert settings.env == "dev"
    assert settings.api_port == 8100
    assert settings.frontend_port == 5180
    assert settings.db_port == 5440
    assert (
        settings.api_bind == "127.0.0.1"
    )  # loopback by default: there is no authentication (ADR-009)
    assert settings.allow_local_providers is False


def test_frontend_allowed_hosts_is_a_known_setting() -> None:
    # The Vite dev server reads this key from the same .env, so the backend must accept it too.
    assert make().frontend_allowed_hosts == "localhost,127.0.0.1"
    assert make(frontend_allowed_hosts="localhost,iw-dev-01").frontend_allowed_hosts.endswith(
        "iw-dev-01"
    )


def test_env_file_with_all_documented_keys_loads(tmp_path: object) -> None:
    from pathlib import Path

    example = Path(__file__).resolve().parents[3] / ".env.example"
    env_file = Path(str(tmp_path)) / ".env"
    env_file.write_text(
        example.read_text().replace("JOBS_RADAR_DB_PASSWORD=", "JOBS_RADAR_DB_PASSWORD=x")
    )
    # Every key in .env.example must be a declared setting (strict mode rejects unknown keys).
    Settings(_env_file=str(env_file))  # type: ignore[call-arg]


def test_database_url_is_built_from_parts() -> None:
    settings = make(db_host="db", db_port=5432, db_name="jr", db_user="u", db_password="p@ss")
    assert settings.database_url == "postgresql+psycopg://u:p%40ss@db:5432/jr"


def test_secrets_never_appear_in_repr_or_str() -> None:
    settings = make(db_password="super-secret-value", credential_key="key-material")
    text = repr(settings) + str(settings)
    assert "super-secret-value" not in text
    assert "key-material" not in text


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make(env="staging")


@pytest.mark.parametrize("port", [0, 70000, -1])
def test_port_range_is_validated(port: int) -> None:
    with pytest.raises(ValidationError):
        make(api_port=port)


def test_test_environment_refuses_a_non_test_database() -> None:
    # Guard against running tests against the development database (CLAUDE.md, ADR-032).
    with pytest.raises(ValidationError, match="test"):
        make(env="test", db_name="jobs_radar")


def test_test_environment_accepts_a_test_database() -> None:
    assert make(env="test", db_name="jobs_radar_test").db_name == "jobs_radar_test"


def test_unknown_values_are_rejected() -> None:
    with pytest.raises(ValidationError):
        make(not_a_setting=1)
