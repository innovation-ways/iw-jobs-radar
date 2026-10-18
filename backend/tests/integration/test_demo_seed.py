"""The demo seed builds a believable world through the real pipeline (own throw-away database)."""

import asyncio
import os
import secrets
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from jobs_radar.core.settings import Settings, get_settings
from jobs_radar.db.session import build_engine, build_session_factory
from jobs_radar.demo.idle_worker import beat_until
from jobs_radar.demo.jobs import JOBS, SOURCES
from jobs_radar.demo.seed import seed_demo
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.services.ai_settings import AiSettingsService
from jobs_radar.services.digest import DigestService
from jobs_radar.services.inbox import InboxFilters, InboxService
from jobs_radar.services.pipeline import PipelineService
from jobs_radar.services.sources import SourceService

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def demo_settings() -> Iterator[Settings]:
    """Settings for a second, private container so the seed never touches the shared test DB."""
    password = secrets.token_urlsafe(16)
    with PostgresContainer(
        "postgres:18", username="demo_test", password=password, dbname="demo_test", driver=None
    ) as container:
        overrides = {
            "JOBS_RADAR_ENV": "test",
            "JOBS_RADAR_DB_HOST": container.get_container_host_ip(),
            "JOBS_RADAR_DB_PORT": str(container.get_exposed_port(5432)),
            "JOBS_RADAR_DB_NAME": "demo_test",
            "JOBS_RADAR_DB_USER": "demo_test",
            "JOBS_RADAR_DB_PASSWORD": password,
            "JOBS_RADAR_CREDENTIAL_KEY": Fernet.generate_key().decode(),
        }
        previous = {key: os.environ.get(key) for key in overrides}
        os.environ.update(overrides)
        get_settings.cache_clear()
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        command.upgrade(config, "head")
        yield get_settings()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def seeded(demo_settings: Settings) -> AsyncIterator[async_sessionmaker]:  # type: ignore[type-arg]
    """The demo database after one seed run."""
    engine: AsyncEngine = build_engine(demo_settings)
    factory = build_session_factory(engine)
    report = await seed_demo(factory, demo_settings)
    assert report.inbox_items > 0
    yield factory
    await engine.dispose()


@pytest.mark.asyncio(loop_scope="session")
async def test_every_board_is_added_and_one_fails(seeded: async_sessionmaker) -> None:  # type: ignore[type-arg]
    async with seeded() as session:
        rows = await SourceService(session, {}).list_with_status(LOCAL_OWNER_ID)
    assert len(rows) == len(SOURCES)
    outcomes = {
        row.source.display_name: row.last_result.outcome if row.last_result else None
        for row in rows
    }
    assert list(outcomes.values()).count("failed") == 1, outcomes


@pytest.mark.asyncio(loop_scope="session")
async def test_inbox_has_scored_jobs_and_a_spread_of_fits(seeded: async_sessionmaker) -> None:  # type: ignore[type-arg]
    async with seeded() as session:
        page = await InboxService(session).list_items(
            LOCAL_OWNER_ID, InboxFilters(state=None, include_closed=True), limit=500
        )
    scored = [row.evaluation.fit_score for row in page.rows if row.evaluation]
    assert len(scored) >= len(JOBS) * 0.7
    assert max(scored) >= 80, "the best demo job should be a strong match"
    assert min(scored) <= 40, "the set-aside tab needs poor fits"
    assert len({row.item.state for row in page.rows}) >= 4, "every inbox state should be visible"


@pytest.mark.asyncio(loop_scope="session")
async def test_digest_has_news_for_today(seeded: async_sessionmaker) -> None:  # type: ignore[type-arg]
    async with seeded() as session:
        digest = await DigestService(session).build(LOCAL_OWNER_ID)
    assert digest.new_high_fit, "good jobs that appear on the last run are today's news"
    assert digest.changed_shortlisted, "a shortlisted job whose pay changed is flagged"
    assert digest.source_health, "the failing board is listed as needing attention"


@pytest.mark.asyncio(loop_scope="session")
async def test_seeding_twice_is_refused(
    seeded: async_sessionmaker, demo_settings: Settings
) -> None:  # type: ignore[type-arg]
    with pytest.raises(RuntimeError, match="empty database"):
        await seed_demo(seeded, demo_settings)


@pytest.mark.asyncio(loop_scope="session")
async def test_job_analysis_is_shown_as_set_up(
    seeded: async_sessionmaker, demo_settings: Settings
) -> None:  # type: ignore[type-arg]
    async with seeded() as session:
        view = await AiSettingsService(session, demo_settings, box=None).get(LOCAL_OWNER_ID)
    assert view.jobs_connection_id is not None
    assert view.mode == "local"


@pytest.mark.asyncio(loop_scope="session")
async def test_the_idle_worker_beats_until_it_is_stopped(seeded: async_sessionmaker) -> None:  # type: ignore[type-arg]
    stop = asyncio.Event()
    task = asyncio.create_task(beat_until(seeded, stop, interval=0.05))
    await asyncio.sleep(0.2)
    stop.set()
    assert await task >= 2


@pytest.mark.asyncio(loop_scope="session")
async def test_nothing_is_waiting_for_analysis_or_scoring(
    seeded: async_sessionmaker, demo_settings: Settings
) -> None:  # type: ignore[type-arg]
    async with seeded() as session:
        status = await PipelineService(session, 90).status(LOCAL_OWNER_ID)
    assert status.analysis.waiting == 0
    assert status.scoring.waiting == 0
    assert status.state != "no_ai"
