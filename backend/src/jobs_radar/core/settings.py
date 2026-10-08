"""Application settings read from the environment (ADR-032).

Every environment-specific value (ports, credentials, URLs) lives here and is supplied
through ``JOBS_RADAR_*`` variables or the untracked ``.env`` file. Nothing is hardcoded elsewhere.
"""

from functools import lru_cache
from typing import Literal, Self
from urllib.parse import quote

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration for the API and the worker.

    Unknown ``JOBS_RADAR_*`` values are rejected so that typos fail loudly at start-up.
    """

    model_config = SettingsConfigDict(
        env_prefix="JOBS_RADAR_",
        # Repository root .env when run from backend/ (alembic, make); real variables always win.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="forbid",
        frozen=True,
    )

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # HTTP exposure. Loopback by default because V1 has no authentication (ADR-009).
    api_bind: str = "127.0.0.1"
    api_port: int = Field(default=8100, ge=1, le=65535)
    frontend_port: int = Field(default=5180, ge=1, le=65535)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://127.0.0.1:5180"])
    # Host names the Vite dev server accepts (read by the frontend from the same .env).
    frontend_allowed_hosts: str = "localhost,127.0.0.1"

    # PostgreSQL
    db_host: str = "127.0.0.1"
    db_port: int = Field(default=5440, ge=1, le=65535)
    # Address the PostgreSQL port is published on (read by Docker Compose); loopback by default.
    db_bind: str = "127.0.0.1"
    db_name: str = "jobs_radar"
    db_user: str = "jobs_radar"
    db_password: SecretStr

    # Secrets and providers
    credential_key: SecretStr | None = None
    ollama_url: str = "http://host.docker.internal:11434"
    allow_local_providers: bool = False

    # Worker
    worker_poll_seconds: int = Field(default=15, ge=1)
    extraction_concurrency: int = Field(default=1, ge=1)
    worker_heartbeat_max_age_seconds: int = Field(default=90, ge=1)

    @property
    def database_url(self) -> str:
        """SQLAlchemy URL for psycopg 3, used by the async engine and by Alembic."""
        user = quote(self.db_user, safe="")
        password = quote(self.db_password.get_secret_value(), safe="")
        return (
            f"postgresql+psycopg://{user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @model_validator(mode="after")
    def _test_environment_needs_a_test_database(self) -> Self:
        """Refuse to run the test environment against anything that is not a test database."""
        if self.env == "test" and not self.db_name.endswith("_test"):
            msg = "JOBS_RADAR_ENV=test requires a database name ending in '_test'"
            raise ValueError(msg)
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, created on first use."""
    return Settings()  # values come from the environment
