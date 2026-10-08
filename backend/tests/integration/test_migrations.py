"""Migrations must apply, roll back and re-apply on an empty database (ADR-030)."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

import jobs_radar.db.models  # noqa: F401  # registers every table on Base.metadata
from jobs_radar.core.settings import Settings, get_settings
from jobs_radar.db.base import Base

pytestmark = pytest.mark.integration

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRATCH_DB = "jobs_radar_migration_test"


@pytest.fixture
def scratch_database(settings: Settings) -> Iterator[str]:
    """Create an empty database next to the test one and point the settings at it."""
    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB}"))
        connection.execute(text(f"CREATE DATABASE {SCRATCH_DB}"))
    previous = os.environ["JOBS_RADAR_DB_NAME"]
    os.environ["JOBS_RADAR_DB_NAME"] = SCRATCH_DB
    get_settings.cache_clear()
    try:
        yield SCRATCH_DB
    finally:
        os.environ["JOBS_RADAR_DB_NAME"] = previous
        get_settings.cache_clear()
        with admin.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
        admin.dispose()


def _tables() -> set[str]:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        names = {row[0] for row in rows}
    engine.dispose()
    return names


def test_upgrade_downgrade_upgrade(scratch_database: str) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))

    expected = set(Base.metadata.tables)

    command.upgrade(config, "head")
    assert _tables() - {"alembic_version"} == expected

    command.downgrade(config, "base")
    assert _tables() - {"alembic_version"} == set()  # everything is removed, nothing left behind

    command.upgrade(config, "head")
    assert _tables() - {"alembic_version"} == expected
