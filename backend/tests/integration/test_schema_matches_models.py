"""The migrated database must match the ORM models exactly (no drift between code and schema)."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

import jobs_radar.db.models  # noqa: F401  # registers every table on Base.metadata
from jobs_radar.core.settings import Settings
from jobs_radar.db.base import Base

pytestmark = pytest.mark.integration


def test_models_and_migrations_have_no_drift(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": False}
        )
        differences = compare_metadata(context, Base.metadata)
    engine.dispose()
    assert differences == [], differences
