"""Integration-test fixtures: one throw-away PostgreSQL container per session (ADR-030, ADR-035).

Integration tests NEVER connect to the development database. The container is started here,
the environment is pointed at it, migrations are applied, and the application and HTTP client
are built once per session and shared.
"""

import os
import secrets
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from jobs_radar.api.app import create_app
from jobs_radar.api.deps import get_session
from jobs_radar.core.settings import Settings, get_settings
from jobs_radar.db.session import build_engine, build_session_factory

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """Start a temporary PostgreSQL container for the whole test session."""
    password = secrets.token_urlsafe(16)
    with PostgresContainer(
        "postgres:18",
        username="jobs_radar_test",
        password=password,
        dbname="jobs_radar_test",
        driver=None,
    ) as container:
        yield container


@pytest.fixture(scope="session", autouse=True)
def _test_environment(postgres_container: PostgresContainer) -> Iterator[None]:
    """Point every setting at the container and apply migrations before any test runs."""
    overrides = {
        "JOBS_RADAR_ENV": "test",
        "JOBS_RADAR_DB_HOST": postgres_container.get_container_host_ip(),
        "JOBS_RADAR_DB_PORT": str(postgres_container.get_exposed_port(5432)),
        "JOBS_RADAR_DB_NAME": "jobs_radar_test",
        "JOBS_RADAR_DB_USER": "jobs_radar_test",
        "JOBS_RADAR_DB_PASSWORD": postgres_container.password,
        "JOBS_RADAR_CREDENTIAL_KEY": Fernet.generate_key().decode(),
        # The suite keeps the vocabulary the migrations leave; the packs have their own tests.
        "JOBS_RADAR_LOAD_PACKS": "false",
    }
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    get_settings.cache_clear()
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head")
    # The suite models an installation that uses the software pack, like the owner's own.
    admin = create_engine(get_settings().database_url)
    with admin.begin() as connection:
        connection.execute(
            text("INSERT INTO owner_pack (owner_id, pack_key) VALUES (1, 'software_data_it')")
        )
    admin.dispose()
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Settings that point at the test container."""
    return get_settings()


@pytest_asyncio.fixture(scope="session")
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Async engine bound to the test container."""
    engine = build_engine(settings)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the test container."""
    return build_session_factory(engine)


@pytest_asyncio.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """A session; tests are responsible for cleaning up what they create."""
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="session")
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    """The application, shared by the whole session. Tests must not assign to ``app.state``."""
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture(scope="session")
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP client talking to the shared application."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest_asyncio.fixture
async def isolated_client(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    """The shared client with every request running in the test's transaction."""
    monkeypatch.setattr(db_session, "commit", db_session.flush)

    async def same_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setitem(app.dependency_overrides, get_session, same_session)
    yield client
