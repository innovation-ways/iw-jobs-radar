"""The worker takes its job-analysis setup from the database (ADR-046), not the environment."""

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobs_radar.core.settings import Settings, get_settings
from jobs_radar.db.models import PrivacySetting, ProviderConnection
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.services.jobs_ai import JobsAiLoader

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def clean(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await session.execute(delete(ProviderConnection))
        await session.execute(delete(PrivacySetting))
        await session.commit()


async def add(session_factory: async_sessionmaker[AsyncSession], **values: object) -> int:
    async with session_factory() as session:
        row = ProviderConnection(
            owner_id=LOCAL_OWNER_ID,
            provider_type="ollama",
            display_name="Local",
            # The loader only accepts the configured local server, which a developer's .env may change.
            endpoint_url=get_settings().ollama_url,
            model_id="qwen3:8b",
            config_json={"embedding_model": "emb-1"},
            **values,
        )
        session.add(row)
        await session.commit()
        return row.provider_connection_id


async def test_no_connection_for_jobs_means_no_ai(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await add(session_factory, is_active=True)  # used for CVs only
    assert await JobsAiLoader(settings, session_factory).load() is None


async def test_the_connection_for_jobs_builds_the_extraction_setup_with_its_models(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await add(session_factory, use_for_jobs=True)
    jobs_ai = await JobsAiLoader(settings, session_factory).load()
    assert jobs_ai is not None
    assert jobs_ai.model == "qwen3:8b" and jobs_ai.embedding_model == "emb-1"


async def test_the_setup_is_reused_until_the_connection_changes(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    connection_id = await add(session_factory, use_for_jobs=True)
    loader = JobsAiLoader(settings, session_factory)
    first = await loader.load()
    assert await loader.load() is first
    async with session_factory() as session:
        row = await session.get(ProviderConnection, connection_id)
        assert row is not None
        row.model_id = "other"
        row.version += 1
        await session.commit()
    changed = await loader.load()
    assert changed is not first and changed is not None and changed.model == "other"


async def test_switching_job_analysis_off_in_the_gui_takes_effect_without_a_restart(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    connection_id = await add(session_factory, use_for_jobs=True)
    loader = JobsAiLoader(settings, session_factory)
    assert await loader.load() is not None
    async with session_factory() as session:
        row = await session.get(ProviderConnection, connection_id)
        assert row is not None
        row.use_for_jobs = False
        await session.commit()
    assert await loader.load() is None
