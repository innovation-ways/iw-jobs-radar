"""Alembic environment: uses the application settings and metadata (ADR-030)."""

from alembic import context
from sqlalchemy import create_engine, pool

import jobs_radar.db.models  # noqa: F401  # registers every table on Base.metadata
from jobs_radar.core.settings import get_settings
from jobs_radar.db.base import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to the database."""
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured database (synchronous psycopg 3 connection)."""
    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
