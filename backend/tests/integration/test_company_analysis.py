"""Deep company analysis: public pages, local model, every statement quoted (ADR-054)."""

import json
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import make_company

from jobs_radar.adapters.enrichment.website import WebPage, WebsiteUnreadableError
from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderError, ProviderOutput
from jobs_radar.adapters.providers.factory import ProviderSpec
from jobs_radar.core.crypto import CredentialBox
from jobs_radar.core.errors import DependencyUnavailableError, InputValidationError, NotFoundError
from jobs_radar.core.settings import Settings
from jobs_radar.db.models import CompanyFact, PrivacySetting, ProviderConnection
from jobs_radar.domain.enums import ProviderErrorClass
from jobs_radar.services.ai_settings import AiSettingsService
from jobs_radar.services.company_analysis import CompanyAnalysisService

pytestmark = pytest.mark.integration

HOME = "https://northwind.example/"
ABOUT = "https://northwind.example/about"


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
        return ProviderOutput(json.dumps(self.world.answer), 4)

    async def available_models(self) -> list[str]:
        return [self.model]


def statement(topic: str, text: str, quote: str, url: str = ABOUT) -> dict[str, str]:
    return {"topic": topic, "text": text, "quote": quote, "page_url": url}


class World:
    def __init__(self) -> None:
        self.requests: list[tuple[ProviderSpec, ExtractionRequest]] = []
        self.error: ProviderError | None = None
        self.visited: list[str] = []
        self.unreadable: WebsiteUnreadableError | None = None
        self.pages = [
            WebPage(HOME, "Northwind builds billing software for telecom operators."),
            WebPage(ABOUT, "Founded in 2015. We are remote-first with a hub in Lisbon."),
        ]
        self.answer: dict[str, object] = {
            "overview": "Northwind sells billing software to telecom operators.",
            "company_type": "product",
            "remote_policy": "remote",
            "statements": [
                statement("offering", "Builds billing software.", "builds billing software", HOME),
                statement("remote_policy", "Remote-first.", "We are remote-first"),
                statement("locations", "Has a Lisbon hub.", "a hub in Lisbon"),
            ],
            "open_questions": ["Salary bands are not published."],
        }

    def build(self, spec: ProviderSpec) -> Chat:
        return Chat(spec, self)

    async def read(self, home_url: str) -> list[WebPage]:
        self.visited.append(home_url)
        if self.unreadable:
            raise self.unreadable
        return self.pages


@pytest.fixture(autouse=True)
async def clean(db_session: AsyncSession) -> None:
    await db_session.execute(delete(ProviderConnection))
    await db_session.execute(delete(PrivacySetting))


async def setup(
    session: AsyncSession, settings: Settings, *, local: bool = True, directions_model: str = ""
) -> tuple[CompanyAnalysisService, World]:
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
        if directions_model:
            await ai.update_connection(
                1,
                row.provider_connection_id,
                expected_version=row.version,
                direction_model=directions_model,
            )
    return CompanyAnalysisService(session, ai, reader=world), world


async def company(session: AsyncSession, homepage: str | None = HOME) -> int:
    c = await make_company(session, "Northwind Labs")
    c.homepage_url = homepage
    session.add(
        CompanyFact(
            company_id=c.company_id,
            fact_key="industry",
            value_json="software industry",
            origin="public_dataset",
            source_name="wikidata",
            source_url=None,
            retrieved_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return c.company_id


async def facts(session: AsyncSession, company_id: int) -> list[CompanyFact]:
    return list(
        (
            await session.execute(
                select(CompanyFact)
                .where(CompanyFact.company_id == company_id, CompanyFact.fact_key == "ai_dossier")
                .order_by(CompanyFact.company_fact_id)
            )
        ).scalars()
    )


async def test_the_dossier_keeps_only_statements_whose_quote_is_on_the_page(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings)
    company_id = await company(db_session)
    world.answer["statements"] = [  # type: ignore[index]
        statement("offering", "Builds billing software.", "builds billing software", HOME),
        statement("culture", "Famous for free lunches.", "free lunches every day"),
        statement("remote_policy", "Remote-first.", "We are remote-first"),
    ]
    fact = await service.analyse(1, company_id)
    assert (fact.fact_key, fact.origin) == ("ai_dossier", "ai_inference")
    assert fact.source_name == "ollama:qwen3:8b" and fact.source_url == HOME
    value = fact.value_json
    assert [s["topic"] for s in value["statements"]] == ["offering", "remote_policy"]
    assert value["dropped"] == 1
    assert value["pages"] == [HOME, ABOUT]
    assert value["open_questions"] == ["Salary bands are not published."]


async def test_a_quote_must_come_from_the_page_it_names(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings)
    company_id = await company(db_session)
    world.answer["statements"] = [  # type: ignore[index]
        statement("offering", "Builds billing software.", "builds billing software", ABOUT),
        statement("remote_policy", "Remote-first.", "We are remote-first"),
    ]
    fact = await service.analyse(1, company_id)
    assert [s["topic"] for s in fact.value_json["statements"]] == ["remote_policy"]


async def test_only_page_text_and_the_company_name_reach_the_local_model(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings)
    company_id = await company(db_session)
    await service.analyse(1, company_id)
    spec, request = world.requests[0]
    assert spec.provider_type == "ollama"
    assert "Northwind Labs" in request.user and ABOUT in request.user
    assert "remote-first with a hub in Lisbon" in request.user
    assert "verbatim" in request.system and "quote" in request.system
    assert world.visited == [HOME]


async def test_a_new_analysis_supersedes_the_old_one(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings)
    company_id = await company(db_session)
    await service.analyse(1, company_id)
    world.answer["open_questions"] = []
    await service.analyse(1, company_id)
    rows = await facts(db_session, company_id)
    assert [r.superseded_at is None for r in rows] == [False, True]


async def test_without_a_website_or_a_local_model_nothing_is_read_or_sent(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings)
    no_site = await company(db_session, homepage=None)
    with pytest.raises(InputValidationError, match="website"):
        await service.analyse(1, no_site)
    await db_session.execute(delete(ProviderConnection))
    await db_session.execute(delete(PrivacySetting))
    service, world = await setup(db_session, settings, local=False)
    with pytest.raises(InputValidationError, match="local model"):
        await service.analyse(1, await company(db_session))
    assert world.requests == [] and world.visited == []


async def test_failures_store_nothing(db_session: AsyncSession, settings: Settings) -> None:
    service, world = await setup(db_session, settings)
    company_id = await company(db_session)
    world.pages = []
    with pytest.raises(DependencyUnavailableError) as no_pages:
        await service.analyse(1, company_id)
    assert no_pages.value.details["error_class"] == "site_unreadable"
    world.pages = [WebPage(HOME, "Northwind builds billing software.")]
    world.error = ProviderError(ProviderErrorClass.UNAVAILABLE, "The model is not reachable.")
    with pytest.raises(DependencyUnavailableError):
        await service.analyse(1, company_id)
    world.error = None
    world.answer = {"statements": [statement("product", "x", "an invented quote")]}
    with pytest.raises(DependencyUnavailableError) as unusable:
        await service.analyse(1, company_id)
    assert unusable.value.details["error_class"] == "invalid_response"
    world.answer = {"nonsense": True}
    with pytest.raises(DependencyUnavailableError):
        await service.analyse(1, company_id)
    assert await facts(db_session, company_id) == []


async def test_an_unknown_company_is_404(db_session: AsyncSession, settings: Settings) -> None:
    service, _ = await setup(db_session, settings)
    with pytest.raises(NotFoundError):
        await service.analyse(1, 999_999)


async def test_a_site_that_refuses_automated_access_is_named_as_such(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings)
    company_id = await company(db_session)
    world.unreadable = WebsiteUnreadableError("refused", 403)
    with pytest.raises(DependencyUnavailableError) as caught:
        await service.analyse(1, company_id)
    assert caught.value.details["error_class"] == "site_refused"
    assert "refused" in caught.value.message and "403" in caught.value.message
    assert world.requests == []
    world.unreadable = WebsiteUnreadableError("robots", None)
    with pytest.raises(DependencyUnavailableError) as robots:
        await service.analyse(1, company_id)
    assert robots.value.details["error_class"] == "site_robots"


async def test_a_page_that_is_too_large_is_named_as_such(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings)
    company_id = await company(db_session)
    world.unreadable = WebsiteUnreadableError("too_large", 200)
    with pytest.raises(DependencyUnavailableError) as caught:
        await service.analyse(1, company_id)
    assert caught.value.details["error_class"] == "site_too_large"
    assert "too large" in caught.value.message and "HTTP" not in caught.value.message


async def test_the_overview_the_kind_of_company_and_the_remote_policy_are_stored(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, _ = await setup(db_session, settings)
    fact = await service.analyse(1, await company(db_session))
    value = fact.value_json
    assert value["overview"] == "Northwind sells billing software to telecom operators."
    assert (value["company_type"], value["remote_policy"]) == ("product", "remote")


async def test_an_unknown_kind_of_company_or_policy_is_normalised(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings)
    world.answer["company_type"] = "unicorn"
    world.answer["remote_policy"] = "sometimes"
    value = (await service.analyse(1, await company(db_session))).value_json
    assert (value["company_type"], value["remote_policy"]) == ("unknown", "not_stated")


async def test_a_statement_that_only_repeats_its_quote_is_dropped(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings)
    world.answer["statements"] = [
        statement("offering", "We are remote-first", "We are remote-first"),
        statement("remote_policy", "Works remotely.", "We are remote-first"),
    ]
    value = (await service.analyse(1, await company(db_session))).value_json
    assert [s["text"] for s in value["statements"]] == ["Works remotely."]
    assert value["dropped"] == 1


async def test_an_answer_without_an_overview_is_refused(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings)
    world.answer["overview"] = " "
    with pytest.raises(DependencyUnavailableError):
        await service.analyse(1, await company(db_session))


async def test_the_larger_model_chosen_for_directions_does_the_analysis(
    db_session: AsyncSession, settings: Settings
) -> None:
    service, world = await setup(db_session, settings, directions_model="qwen3.6:27b")
    fact = await service.analyse(1, await company(db_session))
    assert world.requests[0][0].model == "qwen3.6:27b"
    assert fact.source_name == "ollama:qwen3.6:27b"
