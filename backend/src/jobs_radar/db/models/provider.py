"""AI provider connections; credentials are encrypted and write-only (ADR-033)."""

from datetime import datetime
from typing import Any

from sqlalchemy import Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped

from jobs_radar.db.base import Base, TimestampMixin
from jobs_radar.db.columns import (
    bool_column,
    bytes_column,
    enum_check,
    fk_column,
    json_column,
    pk_column,
    text_column,
    timestamp_column,
    version_column,
)
from jobs_radar.domain.enums import ProviderType


class ProviderConnection(TimestampMixin, Base):
    """Connection metadata for one AI provider. No plaintext secret is ever stored."""

    __tablename__ = "provider_connection"
    __table_args__ = (
        Index(
            "uq_provider_connection_active_per_owner",
            "owner_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        Index(
            "uq_provider_connection_jobs_per_owner",
            "owner_id",
            unique=True,
            postgresql_where=text("use_for_jobs"),
        ),
        enum_check("provider_type", ProviderType),
        {"comment": "AI provider connections; at most one in use for CV import and one for jobs."},
    )

    provider_connection_id: Mapped[int] = pk_column("Surrogate primary key of the connection.")
    owner_id: Mapped[int] = fk_column("owner.owner_id", "Owner of the connection.", index=False)
    provider_type: Mapped[str] = text_column("ollama, openai, minimax or compatible.", length=20)
    display_name: Mapped[str] = text_column("Name shown in the interface.", length=120)
    endpoint_url: Mapped[str | None] = text_column(
        "Base URL of the provider, if configurable.", nullable=True
    )
    model_id: Mapped[str | None] = text_column(
        "Selected model identifier.", length=120, nullable=True
    )
    config_json: Mapped[Any] = json_column("Non-secret provider settings.")
    credential_ciphertext: Mapped[bytes | None] = bytes_column("Encrypted credential (write-only).")
    credential_updated_at: Mapped[datetime | None] = timestamp_column(
        "UTC time at which the credential was last written.", nullable=True
    )
    is_active: Mapped[bool] = bool_column(
        "Whether this connection is the one used to import a CV.", default=False
    )
    use_for_jobs: Mapped[bool] = bool_column(
        "Whether this local connection analyses collected jobs (remote ones never do).",
        default=False,
    )
    version: Mapped[int] = version_column()


class PrivacySetting(TimestampMixin, Base):
    """The owner's privacy policy for remote AI processing (document 08, section 4)."""

    __tablename__ = "privacy_setting"
    __table_args__ = {"comment": "Privacy policy for remote AI calls; one row per owner."}

    privacy_setting_id: Mapped[int] = pk_column("Surrogate primary key of the setting.")
    owner_id: Mapped[int] = fk_column("owner.owner_id", "Owner the policy belongs to.", unique=True)
    redact_contact_details: Mapped[bool] = bool_column(
        "Whether e-mail addresses, phone numbers and links are removed before a remote call.",
        default=True,
    )
    version: Mapped[int] = version_column()


class IntegrationCredential(TimestampMixin, Base):
    """An encrypted, write-only credential for an optional integration such as GitHub."""

    __tablename__ = "integration_credential"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_integration_credential_owner_name"),
        {"comment": "Encrypted credentials of optional integrations (write-only)."},
    )

    integration_credential_id: Mapped[int] = pk_column("Surrogate primary key of the credential.")
    owner_id: Mapped[int] = fk_column("owner.owner_id", "Owner of the credential.", index=False)
    name: Mapped[str] = text_column(
        "Integration the credential belongs to, for example github.", length=40
    )
    credential_ciphertext: Mapped[bytes | None] = bytes_column("Encrypted credential (write-only).")
    credential_updated_at: Mapped[datetime | None] = timestamp_column(
        "UTC time at which the credential was last written.", nullable=True
    )
