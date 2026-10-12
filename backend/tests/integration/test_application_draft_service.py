"""Writing and listing the pre-application drafts: local model only, append-only (ADR-064)."""

import json

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.evaluation_world import World as JobWorld
from tests.evaluation_world import world
from tests.integration.test_company_summary import World as ModelWorld

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.api.deps import get_application_draft_service
from jobs_radar.core.crypto import CredentialBox
from jobs_radar.core.errors import DependencyUnavailableError, InputValidationError, NotFoundError
from jobs_radar.core.settings import Settings
from jobs_radar.db.models import ApplicationDraft, PrivacySetting, ProviderConnection
from jobs_radar.domain.enums import ProviderErrorClass
from jobs_radar.services.ai_settings import AiSettingsService
from jobs_radar.services.application_draft import ApplicationDraftService

pytestmark = pytest.mark.integration

LETTER = " ".join(["I would like to apply for this role."] * 30)


def answer(held: str, **changes: object) -> str:
    """A valid model answer whose evidence names things the sample profile really holds."""
    data: dict[str, object] = {
        "strengths": [
            {"point": "Deep skill match", "evidence": f"{held}, expert, 5 years"},
            {"point": "Architecture background", "evidence": "Solutions Architect at Example Corp"},
            {"point": "Solid studies", "evidence": "Computer Science"},
        ],
        "positioning": "Lead with the architecture background and the matching core skill.",
        "gaps": ["Kubernetes is not shown; mention related exposure."],
        "cover_letter": LETTER,
        "letter_language": "en",
    }
    return json.dumps({**data, **changes})


@pytest.fixture(autouse=True)
async def clean(db_session: AsyncSession) -> None:
    await db_session.execute(delete(ProviderConnection))
    await db_session.execute(delete(PrivacySetting))


async def stored_for(session: AsyncSession, snapshot_id: int) -> list[ApplicationDraft]:
    found = await session.execute(
        select(ApplicationDraft).where(ApplicationDraft.job_snapshot_id == snapshot_id)
    )
    return list(found.scalars())


async def writer(
    session: AsyncSession,
    settings: Settings,
    w: JobWorld,
    *,
    local: bool = True,
    direction_model: str | None = None,
) -> tuple[ApplicationDraftService, ModelWorld]:
    model = ModelWorld()
    model.answer = answer(w.held)
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
    return ApplicationDraftService(session, ai, max_chars=12000), model


async def test_the_local_model_writes_a_draft_and_it_is_stored_with_its_provenance(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id, revision_id, snapshot_id = (
        w.posting.job_posting_id,
        w.profile_revision_id,
        w.snapshot_id,
    )
    service, model = await writer(db_session, settings, w)
    row = await service.generate(posting_id)
    assert model.requests[0][0].provider_type == "ollama"  # never a remote provider
    assert w.held in model.requests[0][1].user  # the profile facts are in the prompt
    assert row.draft_json["letter_language"] == "en"
    stored = await stored_for(db_session, snapshot_id)
    assert [(r.model, r.prompt_version, r.profile_revision_id) for r in stored] == [
        ("qwen3:8b", "application-v1", revision_id)
    ]


async def test_each_request_adds_a_draft_and_the_list_is_newest_first(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id = w.posting.job_posting_id
    service, _ = await writer(db_session, settings, w)
    first = await service.generate(posting_id)
    second = await service.generate(posting_id)
    listed = await service.list_drafts(posting_id)
    assert [r.application_draft_id for r in listed] == [
        second.application_draft_id,
        first.application_draft_id,
    ]


async def test_the_larger_local_model_chosen_for_directions_writes_the_draft(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id = w.posting.job_posting_id
    service, model = await writer(db_session, settings, w, direction_model="qwen3.6:27b")
    await service.generate(posting_id)
    assert model.requests[0][0].model == "qwen3.6:27b"


async def test_without_a_local_model_for_jobs_the_owner_is_told_to_choose_one(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id = w.posting.job_posting_id
    service, _ = await writer(db_session, settings, w, local=False)
    with pytest.raises(InputValidationError, match="local model"):
        await service.generate(posting_id)


async def test_an_unknown_posting_is_not_found(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    service, _ = await writer(db_session, settings, w)
    with pytest.raises(NotFoundError):
        await service.generate(999_999_999)
    with pytest.raises(NotFoundError):
        await service.list_drafts(999_999_999)


async def test_a_model_that_is_down_is_a_503_and_nothing_is_stored(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id, snapshot_id = w.posting.job_posting_id, w.snapshot_id
    service, model = await writer(db_session, settings, w)
    model.error = ProviderError(ProviderErrorClass.UNAVAILABLE, "down")
    with pytest.raises(DependencyUnavailableError, match="reached"):
        await service.generate(posting_id)
    assert await stored_for(db_session, snapshot_id) == []


async def test_an_unusable_answer_is_a_503_and_nothing_is_stored(
    db_session: AsyncSession, settings: Settings
) -> None:
    w = await world(db_session)
    posting_id, snapshot_id = w.posting.job_posting_id, w.snapshot_id
    service, model = await writer(db_session, settings, w)
    model.answer = json.dumps({"strengths": []})
    with pytest.raises(DependencyUnavailableError, match="could not be used"):
        await service.generate(posting_id)
    assert await stored_for(db_session, snapshot_id) == []


class FakeService:
    """Stands in for the service so the route does not commit the test's transaction."""

    async def generate(self, job_posting_id: int) -> ApplicationDraft:
        raise NotFoundError("Job posting not found.")

    async def list_drafts(self, job_posting_id: int) -> list[ApplicationDraft]:
        return []


async def test_the_endpoints_answer_404_for_an_unknown_job_and_an_empty_list(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    app.dependency_overrides[get_application_draft_service] = lambda: FakeService()
    try:
        created = await client.post("/api/v1/jobs/123/application-draft")
        listed = await client.get("/api/v1/jobs/123/application-drafts")
    finally:
        app.dependency_overrides.pop(get_application_draft_service, None)
    assert created.status_code == 404, created.text
    assert listed.status_code == 200 and listed.json() == {"items": []}
