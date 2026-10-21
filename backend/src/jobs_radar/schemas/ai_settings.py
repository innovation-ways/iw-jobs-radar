"""API contracts for AI & privacy settings (document 07, section 6). No credential is returned."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from jobs_radar.schemas.common import StrictModel

ProviderTypeName = Literal["ollama", "openai", "minimax", "compatible"]


class ConnectionCreate(StrictModel):
    """Create a connection; the credential is written separately."""

    provider_type: ProviderTypeName
    display_name: str = Field(min_length=1, max_length=120)
    endpoint_url: str | None = Field(default=None, max_length=500)
    model_id: str | None = Field(default=None, max_length=120)


class ConnectionUpdate(StrictModel):
    """Change non-secret metadata with the version the client saw."""

    expected_version: int = Field(ge=1)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    endpoint_url: str | None = Field(default=None, max_length=500)
    model_id: str | None = Field(default=None, max_length=120)
    # A local model for career directions only; blank goes back to the job model (ADR-057).
    direction_model: str | None = Field(default=None, max_length=120)


class CredentialWrite(StrictModel):
    """The write-only credential. It is never echoed back."""

    secret: str = Field(min_length=1, max_length=500, repr=False)


class ConnectionRead(StrictModel):
    """A connection: metadata and credential *status* only."""

    provider_connection_id: int
    provider_type: ProviderTypeName
    display_name: str
    endpoint_url: str | None
    model_id: str | None
    credential_status: Literal["saved", "none"]
    credential_updated_at: datetime | None
    processing_location: Literal["local", "remote"]
    is_active: bool
    use_for_jobs: bool
    version: int
    direction_model: str | None = None


class PrivacyRead(StrictModel):
    """The privacy policy for remote calls."""

    redact_contact_details: bool
    # Effective value: the owner's switch or the environment (ADR-081).
    allow_local_providers: bool
    # True when the environment allows it, so the switch in the app cannot turn it off.
    local_providers_forced_by_environment: bool
    version: int


class AiSettingsRead(StrictModel):
    """The whole AI & privacy configuration."""

    mode: Literal["no_ai", "local", "remote"]
    import_connection_id: int | None
    jobs_connection_id: int | None
    key_configured: bool
    connections: list[ConnectionRead]
    privacy: PrivacyRead
    integrations: dict[str, Literal["saved", "none"]]


class ConnectionSelect(StrictModel):
    """Choose the connection for CV import or job analysis; ``null`` switches it off."""

    provider_connection_id: int | None = Field(default=None, ge=1)


class ConnectionTestRead(StrictModel):
    """Outcome of a connection test (no document or job content is sent)."""

    ok: bool
    error_class: str | None
    message: str
    models: list[str]


class PrivacyUpdate(StrictModel):
    """Change the privacy policy."""

    redact_contact_details: bool
    # ``null`` leaves the switch as it is.
    allow_local_providers: bool | None = None
    expected_version: int = Field(ge=1)
