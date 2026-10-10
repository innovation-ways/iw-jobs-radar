"""Assessing one job against the owner's directions from the screen: local model only (ADR-057)."""

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
from tests.integration.test_direction_evaluation import BILLING, directions, with_directions

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.api.deps import get_direction_assess_service
from jobs_radar.core.crypto import CredentialBox
from jobs_radar.core.errors import DependencyUnavailableError, InputValidationError
from jobs_radar.core.settings import Settings
from jobs_radar.db.models import PrivacySetting, ProviderConnection
from jobs_radar.domain.enums import ProviderErrorClass
from jobs_radar.services.ai_settings import AiSettingsService
from jobs_radar.services.direction_assess import DirectionAssessService
from jobs_radar.services.direction_service import AssessSummary

pytestmark = pytest.mark.integration

GOOD = {
    "level": "strong",
    "job_quote": "large enterprises in finance and telecom",
    "direction_quote": "billing SME",
}


@pytest.fixture(autouse=True)
async def clean(db_session: AsyncSession) -> None:
    await db_session.execute(delete(ProviderConnection))
    await db_session.execute(delete(PrivacySetting))


async def assessor(
    session: AsyncSession, settings: Settings, *, local: bool = True
) -> tuple[DirectionAssessService, ModelWorld]:
    model = ModelWorld()
    model.answer = json.dumps(GOOD)
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
    return DirectionAssessService(session, ai, max_chars=12000), model


async def test_the_local_model_judges_the_job_and_the_score_is_stored(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id = w.posting.job_posting_id
    await with_directions(db_session, w, directions(("Billing SME", BILLING, True)))
    service, model = await assessor(db_session, settings)
    summary = await service.assess(1, posting_id)
    assert (summary.judged, summary.evaluated) == (1, 1)
    assert model.requests[0][0].provider_type == "ollama"  # never a remote provider


async def test_without_a_local_model_for_jobs_the_owner_is_told_to_choose_one(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id = w.posting.job_posting_id
    service, _ = await assessor(db_session, settings, local=False)
    with pytest.raises(InputValidationError, match="local model"):
        await service.assess(1, posting_id)


async def test_a_model_that_is_down_is_a_503_and_nothing_is_stored(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id = w.posting.job_posting_id
    await with_directions(db_session, w, directions(("Billing SME", BILLING, True)))
    service, model = await assessor(db_session, settings)
    model.error = ProviderError(ProviderErrorClass.UNAVAILABLE, "down")
    with pytest.raises(DependencyUnavailableError):
        await service.assess(1, posting_id)


class FakeAssess:
    """Stands in for the service so the route does not commit the test's transaction."""

    async def assess(self, owner_id: int, job_posting_id: int) -> AssessSummary:
        return AssessSummary(judged=2, evaluated=1)


async def test_the_endpoint_returns_the_summary(client: httpx.AsyncClient, app: FastAPI) -> None:
    app.dependency_overrides[get_direction_assess_service] = lambda: FakeAssess()
    try:
        response = await client.post("/api/v1/jobs/123/assess-directions")
    finally:
        app.dependency_overrides.pop(get_direction_assess_service, None)
    assert response.status_code == 200, response.text
    assert response.json() == {"judged": 2, "evaluated": 1}


async def test_the_model_chosen_for_directions_is_the_one_asked(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id = w.posting.job_posting_id
    await with_directions(db_session, w, directions(("Billing SME", BILLING, True)))
    _, model = await assessor(db_session, settings)
    connection = (
        await db_session.execute(select(ProviderConnection).where(ProviderConnection.use_for_jobs))
    ).scalar_one()
    ai = AiSettingsService(
        db_session,
        settings.model_copy(update={"allow_local_providers": True}),
        box=CredentialBox(SecretStr(Fernet.generate_key().decode())),
        provider_builder=model.build,
    )
    await ai.update_connection(
        1,
        connection.provider_connection_id,
        expected_version=connection.version,
        direction_model="qwen3.6:27b",
    )
    await DirectionAssessService(db_session, ai, max_chars=12000).assess(1, posting_id)
    assert model.requests[-1][0].model == "qwen3.6:27b"
