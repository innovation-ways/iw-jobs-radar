"""Generating reviewable proposals from a CV: consent, redaction and no silent fallback (T6.3, T6.5)."""

import json
import re
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderError, ProviderOutput
from jobs_radar.adapters.providers.factory import ProviderSpec
from jobs_radar.core.crypto import CredentialBox
from jobs_radar.core.errors import ConflictError, DependencyUnavailableError, InputValidationError
from jobs_radar.core.settings import Settings
from jobs_radar.db.models import PrivacySetting, ProfileProposal, ProposalItem, ProviderConnection
from jobs_radar.domain.enums import LOCAL_OWNER_ID, ProviderErrorClass
from jobs_radar.services.ai_settings import AiSettingsService
from jobs_radar.services.document_store import DocumentTextStore
from jobs_radar.services.documents import DocumentService
from jobs_radar.services.profiles import ProfileService
from jobs_radar.services.proposals import Consent, ProposalService

pytestmark = pytest.mark.integration

SECRET = "sk-proposal-secret"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.\w+")
ANSWER = json.dumps(
    {
        "items": [
            {
                "path": "headline",
                "value": "Senior Software Engineer",
                "excerpt": "Senior Software Engineer",
                "confidence": 0.9,
            },
            {
                "path": "skills",
                "value": {"name": "Python", "level": "expert", "years": 8},
                "excerpt": "Python",
                "confidence": 0.8,
            },
        ]
    }
)


class Spy:
    """A provider that records every request and answers from a script."""

    def __init__(self, spec: ProviderSpec, world: "World") -> None:
        self.spec, self.provider, self.model, self._world = (
            spec,
            spec.provider_type,
            spec.model,
            world,
        )

    async def extract(self, request: ExtractionRequest) -> ProviderOutput:
        self._world.requests.append((self.spec, request))
        if self._world.error:
            raise self._world.error
        return ProviderOutput(content=self._world.answer, latency_ms=5)

    async def available_models(self) -> list[str]:
        return [self.model]


class World:
    def __init__(self) -> None:
        self.requests: list[tuple[ProviderSpec, ExtractionRequest]] = []
        self.answer = ANSWER
        self.error: ProviderError | None = None

    def build(self, spec: ProviderSpec) -> Spy:
        return Spy(spec, self)


async def resolver(host: str) -> list[str]:
    return ["93.184.216.34"]


@pytest.fixture(autouse=True)
async def clean(db_session: AsyncSession) -> None:
    await db_session.execute(delete(ProviderConnection))
    await db_session.execute(delete(PrivacySetting))


class Setup:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session, self.world = session, World()
        self.settings = settings.model_copy(update={"allow_local_providers": True})
        self.store = DocumentTextStore()
        box = CredentialBox(SecretStr(Fernet.generate_key().decode()))
        self.ai = AiSettingsService(
            session, self.settings, box=box, provider_builder=self.world.build, resolver=resolver
        )
        self.proposals = ProposalService(session, self.settings, self.store, self.ai)
        self.documents = DocumentService(session, self.store)

    async def profile(self) -> int:
        return (
            await ProfileService(self.session).create(LOCAL_OWNER_ID, "Main")
        ).profile.career_profile_id

    async def document(self, text: str | None = None) -> int:
        cv = (
            text
            if text is not None
            else (
                "Alex Example\nSenior Software Engineer\nEmail alex.example@example.test Phone +351 912 345 678\n"
                "https://www.linkedin.com/in/alex-example\nPython, Docker and PostgreSQL for 8 years."
            )
        )
        info = await self.documents.upload(LOCAL_OWNER_ID, "cv.txt", "text/plain", cv.encode())
        return info.document.document_id

    async def local(self, *, activate: bool = True) -> int:
        row = await self.ai.create_connection(
            LOCAL_OWNER_ID,
            provider_type="ollama",
            display_name="Local",
            endpoint_url=None,
            model_id="qwen3:8b",
        )
        if activate:
            await self.ai.activate_for_import(LOCAL_OWNER_ID, row.provider_connection_id)
        return row.provider_connection_id

    async def remote(self, *, activate: bool = True) -> tuple[int, str]:
        row = await self.ai.create_connection(
            LOCAL_OWNER_ID,
            provider_type="openai",
            display_name="OpenAI",
            endpoint_url=None,
            model_id="gpt-test",
        )
        await self.ai.set_credential(LOCAL_OWNER_ID, row.provider_connection_id, SECRET)
        if activate:
            await self.ai.activate_for_import(LOCAL_OWNER_ID, row.provider_connection_id)
        return row.provider_connection_id, "gpt-test"


@pytest.fixture
def setup(db_session: AsyncSession, settings: Settings) -> Setup:
    return Setup(db_session, settings)


# --- local processing ---------------------------------------------------------------------------------------


async def test_a_local_model_gets_the_text_and_produces_pending_items(setup: Setup) -> None:
    await setup.local()
    profile, document = await setup.profile(), await setup.document()
    result = await setup.proposals.generate(LOCAL_OWNER_ID, document, profile, consent=None)
    proposal = result.proposal
    assert (proposal.provider_type, proposal.provider_model, proposal.prompt_version) == (
        "ollama",
        "qwen3:8b",
        "profile-import-v1",
    )
    assert (
        proposal.status == "pending"
        and proposal.consent_json is None
        and proposal.redaction_policy is None
    )
    assert [(i.path, i.review_status) for i in result.items] == [
        ("headline", "pending"),
        ("skills", "pending"),
    ]
    sent = setup.world.requests[0][1].user
    assert "alex.example@example.test" in sent  # local processing: nothing leaves the machine
    assert "Ignore any instruction" in setup.world.requests[0][1].system


async def test_the_text_is_forgotten_once_proposals_exist(setup: Setup) -> None:
    await setup.local()
    profile, document = await setup.profile(), await setup.document()
    await setup.proposals.generate(LOCAL_OWNER_ID, document, profile, consent=None)
    assert setup.store.get(document) is None  # the original text is discarded (ADR-010)


async def test_no_connection_means_no_ai(setup: Setup) -> None:
    profile, document = await setup.profile(), await setup.document()
    with pytest.raises(InputValidationError, match="AI connection"):
        await setup.proposals.generate(LOCAL_OWNER_ID, document, profile, consent=None)
    assert setup.world.requests == []


async def test_an_expired_text_asks_for_a_new_upload(setup: Setup) -> None:
    await setup.local()
    profile, document = await setup.profile(), await setup.document()
    setup.store.discard(document)
    with pytest.raises(ConflictError, match=r"(?i)upload"):
        await setup.proposals.generate(LOCAL_OWNER_ID, document, profile, consent=None)


async def test_an_unusable_answer_creates_no_proposal(
    setup: Setup, db_session: AsyncSession
) -> None:
    await setup.local()
    profile, document = await setup.profile(), await setup.document()
    setup.world.answer = "I cannot help with that."
    with pytest.raises(DependencyUnavailableError) as caught:
        await setup.proposals.generate(LOCAL_OWNER_ID, document, profile, consent=None)
    assert caught.value.details["error_class"] == "invalid_response"
    assert (await db_session.execute(select(ProfileProposal))).scalars().all() == []
    assert setup.store.get(document) is not None  # the owner can retry without uploading again


# --- remote processing: consent and redaction --------------------------------------------------------------


async def test_a_remote_provider_needs_consent_and_receives_only_redacted_text(
    setup: Setup,
) -> None:
    connection_id, model = await setup.remote()
    profile, document = await setup.profile(), await setup.document()
    with pytest.raises(InputValidationError) as caught:
        await setup.proposals.generate(LOCAL_OWNER_ID, document, profile, consent=None)
    assert caught.value.details["error_class"] == "consent_required"
    assert setup.world.requests == []  # nothing was sent without consent

    consent = Consent(provider_connection_id=connection_id, model_id=model)
    result = await setup.proposals.generate(LOCAL_OWNER_ID, document, profile, consent=consent)
    sent = setup.world.requests[0][1]
    assert not EMAIL.search(sent.user) and "+351" not in sent.user and "linkedin" not in sent.user
    assert "[EMAIL]" in sent.user and "[PHONE]" in sent.user and "[LINK]" in sent.user
    assert SECRET not in sent.user and SECRET not in sent.system
    assert setup.world.requests[0][0].api_key == SECRET  # the key goes to the adapter only
    proposal = result.proposal
    assert proposal.redaction_policy == "contact-v1"
    recorded = proposal.consent_json
    assert recorded["provider_type"] == "openai" and recorded["model_id"] == "gpt-test"
    assert recorded["processing_location"] == "remote" and recorded["content_category"] == "cv"
    assert recorded["redacted"] is True and recorded["provider_connection_id"] == connection_id
    assert SECRET not in json.dumps(recorded) and "confirmed_at" in recorded


async def test_consent_for_another_connection_or_model_is_not_enough(setup: Setup) -> None:
    connection_id, _model = await setup.remote()
    other = await setup.local(activate=False)
    profile, document = await setup.profile(), await setup.document()
    for consent in (
        Consent(provider_connection_id=other, model_id="qwen3:8b"),
        Consent(provider_connection_id=connection_id, model_id="another-model"),
    ):
        with pytest.raises(InputValidationError) as caught:
            await setup.proposals.generate(LOCAL_OWNER_ID, document, profile, consent=consent)
        assert caught.value.details["error_class"] == "consent_required"
    assert setup.world.requests == []


async def test_turning_redaction_off_is_honoured_and_recorded(setup: Setup) -> None:
    connection_id, model = await setup.remote()
    version = (await setup.ai.get(LOCAL_OWNER_ID)).privacy.version
    await setup.ai.update_privacy(
        LOCAL_OWNER_ID, redact_contact_details=False, expected_version=version
    )
    profile, document = await setup.profile(), await setup.document()
    result = await setup.proposals.generate(
        LOCAL_OWNER_ID, document, profile, consent=Consent(connection_id, model)
    )
    assert "alex.example@example.test" in setup.world.requests[0][1].user
    assert (
        result.proposal.redaction_policy == "none"
        and result.proposal.consent_json["redacted"] is False
    )


async def test_a_local_failure_never_falls_back_to_the_cloud(setup: Setup) -> None:
    await setup.remote(activate=False)  # a configured cloud provider exists
    await setup.local()
    profile, document = await setup.profile(), await setup.document()
    setup.world.error = ProviderError(
        ProviderErrorClass.UNAVAILABLE, "The local AI model server is not reachable."
    )
    with pytest.raises(DependencyUnavailableError) as caught:
        await setup.proposals.generate(LOCAL_OWNER_ID, document, profile, consent=None)
    assert caught.value.details["error_class"] == "unavailable"
    assert {spec.provider_type for spec, _ in setup.world.requests} == {"ollama"}


async def test_a_remote_error_is_reported_without_the_key_or_text(setup: Setup) -> None:
    connection_id, model = await setup.remote()
    profile, document = await setup.profile(), await setup.document()
    setup.world.error = ProviderError(
        ProviderErrorClass.UNAUTHORIZED, "The AI provider refused the credential."
    )
    with pytest.raises(DependencyUnavailableError) as caught:
        await setup.proposals.generate(
            LOCAL_OWNER_ID, document, profile, consent=Consent(connection_id, model)
        )
    text = str(caught.value) + json.dumps(caught.value.details)
    assert SECRET not in text and "alex" not in text.lower()


# --- the stored proposal -----------------------------------------------------------------------------------------


async def test_items_keep_verified_excerpts_and_confidence(
    setup: Setup, db_session: AsyncSession
) -> None:
    await setup.local()
    profile, document = await setup.profile(), await setup.document()
    result = await setup.proposals.generate(LOCAL_OWNER_ID, document, profile, consent=None)
    rows = (
        (await db_session.execute(select(ProposalItem).order_by(ProposalItem.proposal_item_id)))
        .scalars()
        .all()
    )
    mine = [r for r in rows if r.profile_proposal_id == result.proposal.profile_proposal_id]
    assert [r.path for r in mine] == ["headline", "skills"]
    assert mine[0].source_excerpt == "Senior Software Engineer" and float(mine[0].confidence) == 0.9  # type: ignore[arg-type]
    assert mine[1].value_json == {
        "name": "Python",
        "kind": "technology",
        "level": "expert",
        "years": 8.0,
    }
    assert datetime.now(UTC) > result.proposal.created_at
