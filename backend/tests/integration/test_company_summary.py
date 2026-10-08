"""AI company summary: labelled inference from public facts and job titles, local model only (T7.4)."""

import json

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import make_company, make_opportunity, make_posting, make_source

from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderError, ProviderOutput
from jobs_radar.adapters.providers.factory import ProviderSpec
from jobs_radar.core.crypto import CredentialBox
from jobs_radar.core.errors import DependencyUnavailableError, InputValidationError, NotFoundError
from jobs_radar.core.settings import Settings
from jobs_radar.db.models import CompanyFact, PrivacySetting, ProviderConnection
from jobs_radar.domain.enums import ProviderErrorClass
from jobs_radar.services.ai_settings import AiSettingsService
from jobs_radar.services.company_summary import CompanySummaryService

pytestmark = pytest.mark.integration


class Chat:
    def __init__(self, spec: ProviderSpec, world: "World") -> None:
        self.spec, self.provider, self.model, self.world = (
            spec,
            spec.provider_type,
            spec.model,
            world,
        )

    async def extract(self, request: ExtractionRequest) -> ProviderOutput:
        self.world.requests.append((self.spec, request))
        if self.world.error:
            raise self.world.error
        return ProviderOutput(self.world.answer, 4)

    async def available_models(self) -> list[str]:
        return [self.model]


class World:
    def __init__(self) -> None:
        self.requests: list[tuple[ProviderSpec, ExtractionRequest]] = []
        self.answer = json.dumps({"summary": "Northwind builds software for telecom billing."})
        self.error: ProviderError | None = None

    def build(self, spec: ProviderSpec) -> Chat:
        return Chat(spec, self)


@pytest.fixture(autouse=True)
async def clean(db_session: AsyncSession) -> None:
    await db_session.execute(delete(ProviderConnection))
    await db_session.execute(delete(PrivacySetting))


async def setup(
    session: AsyncSession, settings: Settings, *, local: bool = True
) -> tuple[CompanySummaryService, World]:
    world = World()
    on = settings.model_copy(update={"allow_local_providers": True})
    ai = AiSettingsService(
        session,
        on,
        box=CredentialBox(SecretStr(Fernet.generate_key().decode())),
        provider_builder=world.build,
    )
    if local:
        row = await ai.create_connection(
            1, provider_type="ollama", display_name="L", endpoint_url=None, model_id="qwen3:8b"
        )
        await ai.activate_for_jobs(1, row.provider_connection_id)
    return CompanySummaryService(session, ai), world


async def company(session: AsyncSession) -> int:
    c = await make_company(session, "Northwind Labs")
    source = await make_source(session, c)
    posting, _ = await make_posting(session, source, title="Billing Platform Engineer")
    await make_opportunity(session, posting)
    session.add(
        CompanyFact(
            company_id=c.company_id,
            fact_key="industry",
            value_json="software industry",
            origin="public_dataset",
            source_name="wikidata",
            source_url=None,
            retrieved_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )
    )
    await session.flush()
    return c.company_id


async def test_the_summary_is_stored_as_a_labelled_inference_from_public_facts_only(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings)
    company_id = await company(db_session)
    fact = await service.generate(1, company_id)
    assert (fact.fact_key, fact.origin, fact.value_json) == (
        "ai_summary",
        "ai_inference",
        "Northwind builds software for telecom billing.",
    )
    assert fact.source_name == "ollama:qwen3:8b" and fact.licence is None
    prompt = world.requests[0][1].user
    assert (
        "Northwind Labs" in prompt
        and "software industry" in prompt
        and "Billing Platform Engineer" in prompt
    )
    assert "Use only the facts below" in world.requests[0][1].system
    assert world.requests[0][0].provider_type == "ollama"  # local model


async def test_a_new_summary_supersedes_the_old_one(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings)
    company_id = await company(db_session)
    await service.generate(1, company_id)
    world.answer = json.dumps({"summary": "A different wording."})
    await service.generate(1, company_id)
    rows = (
        (
            await db_session.execute(
                select(CompanyFact)
                .where(CompanyFact.company_id == company_id, CompanyFact.fact_key == "ai_summary")
                .order_by(CompanyFact.company_fact_id)
            )
        )
        .scalars()
        .all()
    )
    assert [(r.value_json, r.superseded_at is None) for r in rows] == [
        ("Northwind builds software for telecom billing.", False),
        ("A different wording.", True),
    ]


async def test_without_a_local_model_nothing_is_sent(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings, local=False)
    company_id = await company(db_session)
    with pytest.raises(InputValidationError, match="local model"):
        await service.generate(1, company_id)
    assert world.requests == []


async def test_failures_and_unusable_answers_are_reported_and_store_nothing(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings)
    company_id = await company(db_session)
    world.error = ProviderError(
        ProviderErrorClass.UNAVAILABLE, "The local AI model server is not reachable."
    )
    with pytest.raises(DependencyUnavailableError):
        await service.generate(1, company_id)
    world.error = None
    for bad in (
        "not json",
        json.dumps({"summary": ""}),
        json.dumps({"summary": 5}),
        json.dumps({"other": "x"}),
    ):
        world.answer = bad
        with pytest.raises(DependencyUnavailableError) as caught:
            await service.generate(1, company_id)
        assert caught.value.details["error_class"] == "invalid_response"
    rows = (
        (
            await db_session.execute(
                select(CompanyFact).where(
                    CompanyFact.company_id == company_id, CompanyFact.fact_key == "ai_summary"
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows == []


async def test_an_unknown_company_is_404(db_session: AsyncSession, settings: Settings) -> None:
    service, _ = await setup(db_session, settings)
    with pytest.raises(NotFoundError):
        await service.generate(1, 999_999)


async def test_a_long_summary_is_shortened(db_session: AsyncSession, settings: Settings) -> None:
    service, world = await setup(db_session, settings)
    company_id = await company(db_session)
    world.answer = json.dumps({"summary": "word " * 400})
    fact = await service.generate(1, company_id)
    assert len(fact.value_json) <= 700
