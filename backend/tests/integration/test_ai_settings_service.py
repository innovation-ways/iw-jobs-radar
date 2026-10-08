"""AI & privacy settings: connections, write-only credentials, activation and tests (T6.1, T6.2)."""

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.adapters.providers.factory import ProviderSpec
from jobs_radar.core.crypto import CredentialBox
from jobs_radar.core.errors import (
    ConflictError,
    DependencyUnavailableError,
    InputValidationError,
    NotFoundError,
)
from jobs_radar.core.settings import Settings
from jobs_radar.db.models import PrivacySetting, ProviderConnection
from jobs_radar.domain.enums import LOCAL_OWNER_ID, ProviderErrorClass
from jobs_radar.services.ai_settings import AiSettingsService

pytestmark = pytest.mark.integration

SECRET = "sk-test-write-only-123"
PUBLIC = "93.184.216.34"


class FakeProvider:
    """Stands in for a provider: lists models or raises the configured error."""

    def __init__(self, spec: ProviderSpec, models: list[str] | None, error: ProviderError | None):
        self.spec, self._models, self._error = spec, models, error

    async def available_models(self) -> list[str]:
        if self._error:
            raise self._error
        return self._models or []


class Probe:
    """Records what the service built, so tests can see the key reached the adapter only."""

    def __init__(self) -> None:
        self.models: list[str] | None = ["gpt-a", "gpt-b"]
        self.error: ProviderError | None = None
        self.specs: list[ProviderSpec] = []

    def __call__(self, spec: ProviderSpec) -> FakeProvider:
        self.specs.append(spec)
        return FakeProvider(spec, self.models, self.error)


async def resolver(host: str) -> list[str]:
    return {"internal.example.test": ["10.0.0.9"]}.get(host, [PUBLIC])


def service(
    session: AsyncSession, settings: Settings, probe: Probe | None = None, *, key: bool = True
) -> AiSettingsService:
    box = CredentialBox(SecretStr(Fernet.generate_key().decode())) if key else None
    return AiSettingsService(
        session, settings, box=box, provider_builder=probe or Probe(), resolver=resolver
    )


@pytest.fixture(autouse=True)
async def clean(db_session: AsyncSession) -> None:
    await db_session.execute(delete(ProviderConnection))
    await db_session.execute(delete(PrivacySetting))


async def add_openai(svc: AiSettingsService, **overrides: object) -> int:
    values: dict[str, object] = {
        "provider_type": "openai",
        "display_name": "OpenAI",
        "endpoint_url": None,
        "model_id": "gpt-test",
    }
    values.update(overrides)
    connection = await svc.create_connection(LOCAL_OWNER_ID, **values)  # type: ignore[arg-type]
    return connection.provider_connection_id


# --- the default is No AI -------------------------------------------------------------------------------


async def test_the_default_is_no_ai_with_contact_redaction_on(
    db_session: AsyncSession, settings: Settings
) -> None:
    view = await service(db_session, settings).get(LOCAL_OWNER_ID)
    assert view.mode == "no_ai" and view.connections == []
    assert view.privacy.redact_contact_details is True
    assert view.key_configured is True


async def test_an_existing_env_setup_seeds_a_local_connection_once(
    db_session: AsyncSession, settings: Settings
) -> None:
    on = settings.model_copy(
        update={
            "extraction_enabled": True,
            "extraction_model": "qwen3:8b",
            "allow_local_providers": True,
        }
    )
    first = await service(db_session, on).get(LOCAL_OWNER_ID)
    assert [c.provider_type for c in first.connections] == ["ollama"]
    seeded = first.connections[0]
    assert (
        seeded.use_for_jobs is True and seeded.is_active is True and seeded.model_id == "qwen3:8b"
    )
    # the database decides from now on: turning it off is not undone by the env on the next read
    await service(db_session, on).deactivate_jobs(LOCAL_OWNER_ID)
    again = await service(db_session, on).get(LOCAL_OWNER_ID)
    assert len(again.connections) == 1 and again.connections[0].use_for_jobs is False


# --- connections ------------------------------------------------------------------------------------------


async def test_a_connection_is_validated_and_listed_without_any_secret(
    db_session: AsyncSession, settings: Settings
) -> None:
    svc = service(db_session, settings)
    connection_id = await add_openai(svc)
    view = await svc.get(LOCAL_OWNER_ID)
    row = view.connections[0]
    assert row.provider_connection_id == connection_id
    assert row.endpoint_url == "https://api.openai.com/v1"  # default for OpenAI
    assert row.credential_status == "none" and row.processing_location == "remote"


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://api.example.test/v1",
        "https://internal.example.test/v1",
        "https://169.254.169.254/v1",
        "not a url",
    ],
)
async def test_unsafe_endpoints_are_refused(
    db_session: AsyncSession, settings: Settings, endpoint: str
) -> None:
    with pytest.raises(InputValidationError, match=r"address|https|URL|public|resolved"):
        await add_openai(
            service(db_session, settings), provider_type="compatible", endpoint_url=endpoint
        )


async def test_a_compatible_or_minimax_connection_needs_an_endpoint(
    db_session: AsyncSession, settings: Settings
) -> None:
    for kind in ("compatible", "minimax"):
        with pytest.raises(InputValidationError, match="endpoint"):
            await add_openai(service(db_session, settings), provider_type=kind, endpoint_url=None)


async def test_an_ollama_connection_defaults_to_the_configured_local_server(
    db_session: AsyncSession, settings: Settings
) -> None:
    local = settings.model_copy(update={"allow_local_providers": True})
    svc = service(db_session, local)
    created = await svc.create_connection(
        LOCAL_OWNER_ID,
        provider_type="ollama",
        display_name="Local",
        endpoint_url=None,
        model_id="qwen3:8b",
    )
    assert created.endpoint_url == local.ollama_url
    row = (await svc.get(LOCAL_OWNER_ID)).connections[0]
    assert row.processing_location == "local"


async def test_a_local_connection_is_refused_unless_local_providers_are_allowed(
    db_session: AsyncSession, settings: Settings
) -> None:
    off = settings.model_copy(update={"allow_local_providers": False})
    with pytest.raises(InputValidationError, match=r"(?i)local"):
        await service(db_session, off).create_connection(
            LOCAL_OWNER_ID,
            provider_type="ollama",
            display_name="L",
            endpoint_url=None,
            model_id="m",
        )


async def test_updating_metadata_needs_the_current_version(
    db_session: AsyncSession, settings: Settings
) -> None:
    svc = service(db_session, settings)
    connection_id = await add_openai(svc)
    row = (await svc.get(LOCAL_OWNER_ID)).connections[0]
    updated = await svc.update_connection(
        LOCAL_OWNER_ID,
        connection_id,
        expected_version=row.version,
        display_name="Work",
        model_id="gpt-new",
    )
    assert (updated.display_name, updated.model_id, updated.version) == (
        "Work",
        "gpt-new",
        row.version + 1,
    )
    with pytest.raises(ConflictError):
        await svc.update_connection(
            LOCAL_OWNER_ID, connection_id, expected_version=row.version, display_name="x"
        )
    with pytest.raises(NotFoundError):
        await svc.update_connection(LOCAL_OWNER_ID, 999_999, expected_version=1, display_name="x")


# --- credentials: write-only -----------------------------------------------------------------------------------


async def test_a_credential_is_stored_encrypted_and_only_its_status_is_visible(
    db_session: AsyncSession, settings: Settings
) -> None:
    svc = service(db_session, settings)
    connection_id = await add_openai(svc)
    await svc.set_credential(LOCAL_OWNER_ID, connection_id, SECRET)
    stored = (await db_session.execute(select(ProviderConnection))).scalar_one()
    assert (
        stored.credential_ciphertext is not None
        and SECRET.encode() not in stored.credential_ciphertext
    )
    view = await svc.get(LOCAL_OWNER_ID)
    assert view.connections[0].credential_status == "saved"
    assert SECRET not in repr(view)
    await svc.clear_credential(LOCAL_OWNER_ID, connection_id)
    assert (await svc.get(LOCAL_OWNER_ID)).connections[0].credential_status == "none"


async def test_a_credential_cannot_be_stored_without_the_key_or_for_a_local_model(
    db_session: AsyncSession, settings: Settings
) -> None:
    keyless = service(db_session, settings, key=False)
    connection_id = await add_openai(keyless)
    with pytest.raises(DependencyUnavailableError, match="JOBS_RADAR_CREDENTIAL_KEY"):
        await keyless.set_credential(LOCAL_OWNER_ID, connection_id, SECRET)
    local = settings.model_copy(update={"allow_local_providers": True})
    svc = service(db_session, local)
    ollama = await svc.create_connection(
        LOCAL_OWNER_ID, provider_type="ollama", display_name="L", endpoint_url=None, model_id="m"
    )
    with pytest.raises(InputValidationError, match="credential"):
        await svc.set_credential(LOCAL_OWNER_ID, ollama.provider_connection_id, SECRET)
    with pytest.raises(InputValidationError, match="empty"):
        await svc.set_credential(LOCAL_OWNER_ID, connection_id, "   ")


# --- activation ----------------------------------------------------------------------------------------------------


async def test_only_one_connection_imports_cvs_and_a_remote_one_needs_its_credential(
    db_session: AsyncSession, settings: Settings
) -> None:
    svc = service(db_session, settings)
    first = await add_openai(svc, display_name="A")
    second = await add_openai(svc, display_name="B")
    with pytest.raises(InputValidationError, match="credential"):
        await svc.activate_for_import(LOCAL_OWNER_ID, first)
    await svc.set_credential(LOCAL_OWNER_ID, first, SECRET)
    await svc.set_credential(LOCAL_OWNER_ID, second, SECRET)
    await svc.activate_for_import(LOCAL_OWNER_ID, first)
    await svc.activate_for_import(LOCAL_OWNER_ID, second)
    rows = {c.provider_connection_id: c for c in (await svc.get(LOCAL_OWNER_ID)).connections}
    assert (rows[first].is_active, rows[second].is_active) == (False, True)
    assert (await svc.get(LOCAL_OWNER_ID)).mode == "remote"
    await svc.deactivate_import(LOCAL_OWNER_ID)
    assert (await svc.get(LOCAL_OWNER_ID)).mode == "no_ai"


async def test_job_analysis_is_local_only(db_session: AsyncSession, settings: Settings) -> None:
    local = settings.model_copy(update={"allow_local_providers": True})
    svc = service(db_session, local)
    remote = await add_openai(svc)
    await svc.set_credential(LOCAL_OWNER_ID, remote, SECRET)
    with pytest.raises(InputValidationError, match="local"):
        await svc.activate_for_jobs(LOCAL_OWNER_ID, remote)
    ollama = await svc.create_connection(
        LOCAL_OWNER_ID, provider_type="ollama", display_name="L", endpoint_url=None, model_id="m"
    )
    await svc.activate_for_jobs(LOCAL_OWNER_ID, ollama.provider_connection_id)
    assert (await svc.get(LOCAL_OWNER_ID)).jobs_connection_id == ollama.provider_connection_id


async def test_deleting_a_connection_removes_its_credential(
    db_session: AsyncSession, settings: Settings
) -> None:
    svc = service(db_session, settings)
    connection_id = await add_openai(svc)
    await svc.set_credential(LOCAL_OWNER_ID, connection_id, SECRET)
    await svc.delete_connection(LOCAL_OWNER_ID, connection_id)
    assert (await db_session.execute(select(ProviderConnection))).scalars().all() == []


# --- testing a connection ---------------------------------------------------------------------------------------------


async def test_a_connection_test_lists_models_and_hands_the_key_only_to_the_adapter(
    db_session: AsyncSession, settings: Settings
) -> None:
    probe = Probe()
    svc = service(db_session, settings, probe)
    connection_id = await add_openai(svc)
    await svc.set_credential(LOCAL_OWNER_ID, connection_id, SECRET)
    result = await svc.test_connection(LOCAL_OWNER_ID, connection_id)
    assert result.ok is True and result.models == ["gpt-a", "gpt-b"]
    assert probe.specs[-1].api_key == SECRET
    assert SECRET not in repr(result)


async def test_a_failed_connection_test_reports_the_class_and_allows_a_manual_model(
    db_session: AsyncSession, settings: Settings
) -> None:
    probe = Probe()
    probe.error = ProviderError(
        ProviderErrorClass.UNAUTHORIZED, "The AI provider refused the credential."
    )
    svc = service(db_session, settings, probe)
    connection_id = await add_openai(svc)
    await svc.set_credential(LOCAL_OWNER_ID, connection_id, SECRET)
    result = await svc.test_connection(LOCAL_OWNER_ID, connection_id)
    assert (result.ok, result.error_class, result.models) == (False, "unauthorized", [])
    # a provider that cannot list models still works with a typed model id
    updated = await svc.update_connection(
        LOCAL_OWNER_ID,
        connection_id,
        expected_version=(await svc.get(LOCAL_OWNER_ID)).connections[0].version,
        model_id="my-model",
    )
    assert updated.model_id == "my-model"


async def test_testing_a_remote_connection_without_a_credential_is_refused(
    db_session: AsyncSession, settings: Settings
) -> None:
    svc = service(db_session, settings)
    connection_id = await add_openai(svc)
    with pytest.raises(InputValidationError, match="credential"):
        await svc.test_connection(LOCAL_OWNER_ID, connection_id)


# --- privacy -------------------------------------------------------------------------------------------------------------


async def test_the_privacy_policy_is_versioned(
    db_session: AsyncSession, settings: Settings
) -> None:
    svc = service(db_session, settings)
    seen = (await svc.get(LOCAL_OWNER_ID)).privacy.version
    changed = await svc.update_privacy(
        LOCAL_OWNER_ID, redact_contact_details=False, expected_version=seen
    )
    assert changed.redact_contact_details is False and changed.version == seen + 1
    with pytest.raises(ConflictError):
        await svc.update_privacy(LOCAL_OWNER_ID, redact_contact_details=True, expected_version=seen)
