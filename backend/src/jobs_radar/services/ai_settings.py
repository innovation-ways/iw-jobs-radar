"""AI & privacy settings: provider connections, write-only credentials and the privacy policy.

Default is **No AI** (ADR-004). A connection is *local* (Ollama) or *remote* (OpenAI, MiniMax or any
OpenAI-compatible server). One connection is used to import a CV (``is_active``) and one *local*
connection analyses collected jobs (``use_for_jobs``): public job text never goes to a remote
provider (ADR-046). Credentials are encrypted with Fernet (ADR-033), accepted only by write
endpoints, and never returned, logged or shown again. Endpoints are validated against SSRF
(ADR-035) when saved. The environment only seeds the first local connection (ADR-046).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.adapters.providers.factory import ChatProvider, ProviderSpec, build_provider
from jobs_radar.core.crypto import CredentialBox, CredentialKeyError
from jobs_radar.core.errors import (
    ConflictError,
    DependencyUnavailableError,
    InputValidationError,
    NotFoundError,
)
from jobs_radar.core.settings import Settings
from jobs_radar.core.url_guard import BlockedUrlError, Resolver, UrlGuard, system_resolver
from jobs_radar.db.models import PrivacySetting, ProviderConnection
from jobs_radar.repositories.providers import ProviderRepository

ProviderBuilder = Callable[[ProviderSpec], ChatProvider]

# Default endpoint per provider type; the others must be given by the owner.
_DEFAULT_ENDPOINTS = {"openai": "https://api.openai.com/v1"}
_LOCAL_TYPES = {"ollama"}
Mode = Literal["no_ai", "local", "remote"]


@dataclass(frozen=True)
class ConnectionView:
    """A connection as the interface sees it: never the credential, only its status."""

    provider_connection_id: int
    provider_type: str
    display_name: str
    endpoint_url: str | None
    model_id: str | None
    credential_status: Literal["saved", "none"]
    credential_updated_at: datetime | None
    processing_location: Literal["local", "remote"]
    is_active: bool
    use_for_jobs: bool
    version: int


@dataclass(frozen=True)
class AiSettingsView:
    """Everything the AI & privacy screen shows."""

    mode: Mode
    connections: list[ConnectionView]
    import_connection_id: int | None
    jobs_connection_id: int | None
    privacy: PrivacySetting
    key_configured: bool


@dataclass(frozen=True)
class ConnectionTest:
    """Outcome of a connection test. It carries no secret and no prompt."""

    ok: bool
    error_class: str | None
    message: str
    models: list[str]


def connection_view(connection: ProviderConnection) -> ConnectionView:
    """Map a connection to the safe view (credential status only)."""
    return ConnectionView(
        provider_connection_id=connection.provider_connection_id,
        provider_type=connection.provider_type,
        display_name=connection.display_name,
        endpoint_url=connection.endpoint_url,
        model_id=connection.model_id,
        credential_status="saved" if connection.credential_ciphertext else "none",
        credential_updated_at=connection.credential_updated_at,
        processing_location="local" if connection.provider_type in _LOCAL_TYPES else "remote",
        is_active=connection.is_active,
        use_for_jobs=connection.use_for_jobs,
        version=connection.version,
    )


def build_credential_box(settings: Settings) -> CredentialBox | None:
    """Return the credential box for the deployment, or ``None`` without a valid key."""
    try:
        return CredentialBox(settings.credential_key)
    except CredentialKeyError:
        return None


class AiSettingsService:
    """Use cases of the AI & privacy screen. The caller owns the transaction."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        box: CredentialBox | None,
        provider_builder: ProviderBuilder | None = None,
        resolver: Resolver = system_resolver,
    ) -> None:
        self._session = session
        self._settings = settings
        self._box = box
        self._repository = ProviderRepository(session)
        self._build: ProviderBuilder = provider_builder or (
            lambda spec: build_provider(spec, settings)
        )
        self._resolver = resolver

    # --- reading -------------------------------------------------------------------------------

    async def get(self, owner_id: int) -> AiSettingsView:
        """Return the current configuration, seeding it from the environment on first use."""
        privacy, first_use = await self._repository.privacy(owner_id)
        if first_use and self._settings.extraction_enabled:
            await self._seed_local(owner_id)
        connections = await self._repository.list(owner_id)
        views = [connection_view(c) for c in connections]
        active = next((v for v in views if v.is_active), None)
        mode: Mode = "no_ai" if active is None else active.processing_location
        return AiSettingsView(
            mode=mode,
            connections=views,
            import_connection_id=active.provider_connection_id if active else None,
            jobs_connection_id=next(
                (v.provider_connection_id for v in views if v.use_for_jobs), None
            ),
            privacy=privacy,
            key_configured=self._box is not None,
        )

    async def _seed_local(self, owner_id: int) -> None:
        """Turn the environment's extraction setup into the first (local) connection."""
        await self._repository.add(
            ProviderConnection(
                owner_id=owner_id,
                provider_type="ollama",
                display_name="Local Ollama",
                endpoint_url=self._settings.ollama_url,
                model_id=self._settings.extraction_model,
                config_json={"embedding_model": self._settings.embedding_model},
                is_active=True,
                use_for_jobs=True,
            )
        )

    # --- connections ---------------------------------------------------------------------------

    async def _validated_endpoint(self, provider_type: str, endpoint: str | None) -> str:
        """Return a safe endpoint for the type, or raise a validation error."""
        if provider_type in _LOCAL_TYPES:
            return self._validated_local(endpoint)
        url = endpoint or _DEFAULT_ENDPOINTS.get(provider_type)
        if not url:
            msg = f"A {provider_type} connection needs an endpoint URL."
            raise InputValidationError(msg)
        try:
            await UrlGuard(resolver=self._resolver).check(url)
        except BlockedUrlError as exc:
            raise InputValidationError(str(exc)) from exc
        return url.rstrip("/")

    def _validated_local(self, endpoint: str | None) -> str:
        # A local model server may only be the one the deployment configured (ADR-035).
        if not self._settings.allow_local_providers:
            msg = "Local providers are turned off (JOBS_RADAR_ALLOW_LOCAL_PROVIDERS)."
            raise InputValidationError(msg)
        configured = self._settings.ollama_url.rstrip("/")
        if endpoint and endpoint.rstrip("/") != configured:
            msg = "A local connection can only use the local server configured for this deployment."
            raise InputValidationError(msg)
        return configured

    async def create_connection(
        self,
        owner_id: int,
        *,
        provider_type: str,
        display_name: str,
        endpoint_url: str | None,
        model_id: str | None,
    ) -> ProviderConnection:
        """Create a connection (no credential yet, not in use)."""
        endpoint = await self._validated_endpoint(provider_type, endpoint_url)
        await self._repository.privacy(owner_id)
        return await self._repository.add(
            ProviderConnection(
                owner_id=owner_id,
                provider_type=provider_type,
                display_name=display_name.strip(),
                endpoint_url=endpoint,
                model_id=model_id.strip() if model_id else None,
                config_json={},
            )
        )

    async def _connection(
        self, owner_id: int, provider_connection_id: int, *, lock: bool = True
    ) -> ProviderConnection:
        connection = await self._repository.get(owner_id, provider_connection_id, for_update=lock)
        if connection is None:
            msg = f"Connection {provider_connection_id} does not exist."
            raise NotFoundError(msg)
        return connection

    async def update_connection(
        self,
        owner_id: int,
        provider_connection_id: int,
        *,
        expected_version: int,
        display_name: str | None = None,
        endpoint_url: str | None = None,
        model_id: str | None = None,
    ) -> ProviderConnection:
        """Change the non-secret metadata, checking the version the owner saw."""
        connection = await self._connection(owner_id, provider_connection_id)
        self._check_version(connection.version, expected_version, "connection")
        if endpoint_url is not None:
            connection.endpoint_url = await self._validated_endpoint(
                connection.provider_type, endpoint_url
            )
        if display_name is not None:
            connection.display_name = display_name.strip()
        if model_id is not None:
            connection.model_id = model_id.strip() or None
        self._touch(connection)
        await self._session.flush()
        return connection

    async def delete_connection(self, owner_id: int, provider_connection_id: int) -> None:
        """Delete a connection together with its encrypted credential."""
        await self._repository.delete(await self._connection(owner_id, provider_connection_id))

    @staticmethod
    def _check_version(current: int, expected: int, what: str) -> None:
        if current != expected:
            msg = f"The {what} changed since it was loaded."
            raise ConflictError(msg, details={"expected": expected, "actual": current})

    @staticmethod
    def _touch(connection: ProviderConnection) -> None:
        connection.version += 1
        connection.updated_at = datetime.now(UTC)

    # --- credentials (write-only) --------------------------------------------------------------

    async def set_credential(
        self, owner_id: int, provider_connection_id: int, secret: str
    ) -> ConnectionView:
        """Encrypt and store the credential. It can never be read back."""
        connection = await self._connection(owner_id, provider_connection_id)
        if connection.provider_type in _LOCAL_TYPES:
            msg = "A local connection does not take a credential."
            raise InputValidationError(msg)
        if not secret.strip():
            msg = "The credential is empty."
            raise InputValidationError(msg)
        if self._box is None:
            msg = "JOBS_RADAR_CREDENTIAL_KEY is not configured, so credentials cannot be stored."
            raise DependencyUnavailableError(msg)
        connection.credential_ciphertext = self._box.encrypt(secret)
        connection.credential_updated_at = datetime.now(UTC)
        self._touch(connection)
        await self._session.flush()
        return connection_view(connection)

    async def clear_credential(self, owner_id: int, provider_connection_id: int) -> ConnectionView:
        """Delete the stored credential; a remote connection in use is switched off first."""
        connection = await self._connection(owner_id, provider_connection_id)
        connection.credential_ciphertext = None
        connection.credential_updated_at = None
        if connection.provider_type not in _LOCAL_TYPES:
            connection.is_active = False  # no credential, no remote use
        self._touch(connection)
        await self._session.flush()
        return connection_view(connection)

    # --- activation ----------------------------------------------------------------------------

    async def activate_for_import(self, owner_id: int, provider_connection_id: int) -> None:
        """Use this connection to import a CV (a remote one needs its credential)."""
        connection = await self._connection(owner_id, provider_connection_id)
        if connection.provider_type not in _LOCAL_TYPES and not connection.credential_ciphertext:
            msg = "Save the credential before using a remote connection."
            raise InputValidationError(msg)
        if not connection.model_id:
            msg = "Choose a model before using this connection."
            raise InputValidationError(msg)
        await self._repository.clear_flag(owner_id, "is_active")
        connection = await self._connection(owner_id, provider_connection_id)
        connection.is_active = True
        self._touch(connection)
        await self._session.flush()

    async def deactivate_import(self, owner_id: int) -> None:
        """Back to No AI for CV import."""
        await self._repository.clear_flag(owner_id, "is_active")

    async def activate_for_jobs(self, owner_id: int, provider_connection_id: int) -> None:
        """Analyse collected jobs with this connection (local only)."""
        connection = await self._connection(owner_id, provider_connection_id)
        if connection.provider_type not in _LOCAL_TYPES:
            msg = (
                "Job analysis uses a local model only; job text is never sent to a remote provider."
            )
            raise InputValidationError(msg)
        if not connection.model_id:
            msg = "Choose a model before using this connection."
            raise InputValidationError(msg)
        await self._repository.clear_flag(owner_id, "use_for_jobs")
        connection = await self._connection(owner_id, provider_connection_id)
        connection.use_for_jobs = True
        self._touch(connection)
        await self._session.flush()

    async def deactivate_jobs(self, owner_id: int) -> None:
        """Stop analysing collected jobs (they stay collected and show as not evaluated)."""
        await self._repository.clear_flag(owner_id, "use_for_jobs")

    # --- use ------------------------------------------------------------------------------------

    async def import_target(self, owner_id: int) -> tuple[ProviderConnection, ChatProvider] | None:
        """Return the connection chosen for CV import and its adapter, or ``None`` for No AI."""
        connection = next((c for c in await self._repository.list(owner_id) if c.is_active), None)
        if connection is None:
            return None
        return connection, self._build(self.spec_for(connection))

    async def redaction_enabled(self, owner_id: int) -> bool:
        """Whether contact details are removed before a remote call."""
        setting, _ = await self._repository.privacy(owner_id)
        return setting.redact_contact_details

    # --- testing -------------------------------------------------------------------------------

    def spec_for(self, connection: ProviderConnection) -> ProviderSpec:
        """Return the hand-over to the adapter, with the decrypted key (remote connections only)."""
        key: str | None = None
        if connection.credential_ciphertext:
            if self._box is None:
                msg = "JOBS_RADAR_CREDENTIAL_KEY is not configured."
                raise DependencyUnavailableError(msg)
            try:
                key = self._box.decrypt(connection.credential_ciphertext)
            except CredentialKeyError as exc:
                raise DependencyUnavailableError(str(exc)) from exc
        return ProviderSpec(
            provider_type=connection.provider_type,
            base_url=connection.endpoint_url or "",
            model=connection.model_id or "",
            api_key=key,
        )

    async def test_connection(self, owner_id: int, provider_connection_id: int) -> ConnectionTest:
        """Check reachability and list models. Sends no document or job content."""
        connection = await self._connection(owner_id, provider_connection_id, lock=False)
        if connection.provider_type not in _LOCAL_TYPES and not connection.credential_ciphertext:
            msg = "Save the credential before testing a remote connection."
            raise InputValidationError(msg)
        provider = self._build(self.spec_for(connection))
        try:
            models = await provider.available_models()
        except ProviderError as error:
            return ConnectionTest(False, error.error_class.value, error.message, [])
        return ConnectionTest(True, None, f"Connected; {len(models)} models available.", models)

    # --- privacy -------------------------------------------------------------------------------

    async def update_privacy(
        self, owner_id: int, *, redact_contact_details: bool, expected_version: int
    ) -> PrivacySetting:
        """Change the remote-call privacy policy."""
        setting, _ = await self._repository.privacy(owner_id)
        self._check_version(setting.version, expected_version, "privacy setting")
        setting.redact_contact_details = redact_contact_details
        setting.version += 1
        setting.updated_at = datetime.now(UTC)
        await self._session.flush()
        return setting
