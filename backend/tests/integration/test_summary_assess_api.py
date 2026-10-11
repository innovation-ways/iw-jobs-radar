"""Writing the summary of one job from the screen: local model only (ADR-059)."""

import json

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.evaluation_world import world
from tests.integration.test_company_summary import World as ModelWorld

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.api.deps import get_summary_assess_service
from jobs_radar.core.crypto import CredentialBox
from jobs_radar.core.errors import DependencyUnavailableError, InputValidationError
from jobs_radar.core.settings import Settings
from jobs_radar.db.models import JobSummary, PrivacySetting, ProviderConnection
from jobs_radar.domain.enums import ProviderErrorClass
from jobs_radar.services.ai_settings import AiSettingsService
from jobs_radar.services.job_summary import SummaryResult
from jobs_radar.services.summary_assess import SummaryAssessService

pytestmark = pytest.mark.integration

TEXT = (
    "Acme is hiring a senior AI engineer, fully remote within the EU, on a 12-month contract.\n\n"
    "You would design and evaluate LLM-powered features. The posting does not state the pay."
)


@pytest.fixture(autouse=True)
async def clean(db_session: AsyncSession) -> None:
    await db_session.execute(delete(ProviderConnection))
    await db_session.execute(delete(PrivacySetting))


async def stored_for(session: AsyncSession, snapshot_id: int) -> list[JobSummary]:
    found = await session.execute(
        select(JobSummary).where(JobSummary.job_snapshot_id == snapshot_id)
    )
    return list(found.scalars())


async def assessor(
    session: AsyncSession,
    settings: Settings,
    *,
    local: bool = True,
    direction_model: str | None = None,
) -> tuple[SummaryAssessService, ModelWorld]:
    model = ModelWorld()
    model.answer = json.dumps({"summary": TEXT})
    ai = AiSettingsService(
        session,
        settings.model_copy(update={"allow_local_providers": True}),
        box=CredentialBox(SecretStr(Fernet.generate_key().decode())),
        provider_builder=model.build,
    )
    if local:
        row = await ai.create_connection(
            1, provider_type="ollama", display_name="L", endpoint_url=None, model_id="qwen3:8b"
        )
        await ai.activate_for_jobs(1, row.provider_connection_id)
        if direction_model:
            await ai.update_connection(
                1,
                row.provider_connection_id,
                expected_version=row.version,
                direction_model=direction_model,
            )
    return SummaryAssessService(session, ai, max_chars=12000), model


async def test_the_local_model_writes_the_summary_and_it_is_stored(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id = w.posting.job_posting_id  # read before the services touch the session
    service, model = await assessor(db_session, settings)
    result = await service.summarise(posting_id)
    assert (result.text, result.created) == (TEXT, True)
    assert model.requests[0][0].provider_type == "ollama"  # never a remote provider
    stored = await stored_for(db_session, w.snapshot_id)
    assert [row.model for row in stored] == ["qwen3:8b"]


async def test_the_larger_local_model_chosen_for_directions_writes_the_summaries(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id = w.posting.job_posting_id
    service, model = await assessor(db_session, settings, direction_model="qwen3.6:27b")
    await service.summarise(posting_id)
    assert model.requests[0][0].model == "qwen3.6:27b"  # faithful prose needs the larger model


async def test_without_a_local_model_for_jobs_the_owner_is_told_to_choose_one(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id = w.posting.job_posting_id
    service, _ = await assessor(db_session, settings, local=False)
    with pytest.raises(InputValidationError, match="local model"):
        await service.summarise(posting_id)


async def test_a_model_that_is_down_is_a_503_and_nothing_is_stored(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id = w.posting.job_posting_id  # read before the services touch the session
    service, model = await assessor(db_session, settings)
    model.error = ProviderError(ProviderErrorClass.UNAVAILABLE, "down")
    with pytest.raises(DependencyUnavailableError):
        await service.summarise(posting_id)
    assert await stored_for(db_session, w.snapshot_id) == []


async def test_an_unusable_answer_is_a_503_too(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id = w.posting.job_posting_id  # read before the services touch the session
    service, model = await assessor(db_session, settings)
    model.answer = json.dumps({"summary": "too short"})
    with pytest.raises(DependencyUnavailableError, match="summary"):
        await service.summarise(posting_id)


class FakeAssess:
    """Stands in for the service so the route does not commit the test's transaction."""

    async def summarise(self, job_posting_id: int) -> SummaryResult:
        return SummaryResult(TEXT, created=True)


async def test_the_endpoint_returns_the_summary(client: httpx.AsyncClient, app: FastAPI) -> None:
    app.dependency_overrides[get_summary_assess_service] = lambda: FakeAssess()
    try:
        response = await client.post("/api/v1/jobs/123/summary")
    finally:
        app.dependency_overrides.pop(get_summary_assess_service, None)
    assert response.status_code == 200, response.text
    assert response.json() == {"summary": TEXT, "created": True}
