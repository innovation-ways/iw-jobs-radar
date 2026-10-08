"""Async engine and session factory construction (ADR-030)."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from jobs_radar.core.settings import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    """Create the async engine. No connection is opened until the first query."""
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create the session factory; sessions do not expire objects on commit."""
    return async_sessionmaker(engine, expire_on_commit=False)
