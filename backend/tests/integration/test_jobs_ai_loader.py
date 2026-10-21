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


async def add(
    session_factory: async_sessionmaker[AsyncSession],
    config: dict[str, object] | None = None,
    **values: object,
) -> int:
    async with session_factory() as session:
        row = ProviderConnection(
            owner_id=LOCAL_OWNER_ID,
            provider_type="ollama",
            display_name="Local",
            # The loader only accepts the configured local server, which a developer's .env may change.
            endpoint_url=get_settings().ollama_url,
            model_id="qwen3:8b",
            config_json={"embedding_model": "emb-1", **(config or {})},
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


async def test_career_directions_use_the_job_model_unless_another_is_chosen(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await add(session_factory, use_for_jobs=True)
    default = await JobsAiLoader(settings, session_factory).load()
    assert default is not None and default.direction_model == "qwen3:8b"


async def test_a_direction_model_is_used_for_directions_and_the_job_model_for_the_rest(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    connection_id = await add(
        session_factory, config={"direction_model": "big-model"}, use_for_jobs=True
    )
    loader = JobsAiLoader(settings, session_factory)
    first = await loader.load()
    assert first is not None
    assert (first.model, first.direction_model) == ("qwen3:8b", "big-model")
    async with session_factory() as session:
        row = await session.get(ProviderConnection, connection_id)
        assert row is not None
        row.config_json = {"embedding_model": "emb-1", "direction_model": "bigger"}
        row.version += 1
        await session.commit()
    changed = await loader.load()
    assert changed is not None and changed.direction_model == "bigger"


async def test_the_setup_includes_the_summary_runner(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await add(session_factory, use_for_jobs=True)
    setup = await JobsAiLoader(settings, session_factory).load()
    assert setup is not None and setup.summaries is not None


async def test_summaries_use_the_direction_model_and_default_to_the_job_model(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    connection_id = await add(session_factory, use_for_jobs=True)
    loader = JobsAiLoader(settings, session_factory)
    default = await loader.load()
    assert default is not None and default.summaries.model == "qwen3:8b"
    async with session_factory() as session:
        row = await session.get(ProviderConnection, connection_id)
        assert row is not None
        row.config_json = {"direction_model": "big-model"}
        row.version += 1
        await session.commit()
    changed = await loader.load()
    assert changed is not None and changed.summaries.model == "big-model"
    assert changed.model == "qwen3:8b"  # extraction keeps the job model


async def test_allowing_local_providers_in_the_app_rebuilds_the_setup_without_a_restart(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    off = settings.model_copy(update={"allow_local_providers": False})
    await add(session_factory, use_for_jobs=True)
    loader = JobsAiLoader(off, session_factory)
    first = await loader.load()
    assert first is not None
    async with session_factory() as session:
        session.add(PrivacySetting(owner_id=LOCAL_OWNER_ID, allow_local_providers=True))
        await session.commit()
    again = await loader.load()
    assert again is not None and again is not first
