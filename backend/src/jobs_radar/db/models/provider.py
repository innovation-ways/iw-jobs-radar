"""AI provider connections; credentials are encrypted and write-only (ADR-033)."""

from datetime import datetime
from typing import Any

from sqlalchemy import Index, text
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
        enum_check("provider_type", ProviderType),
        {"comment": "AI provider connections; at most one active per owner."},
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
        "Whether this connection is the one in use.", default=False
    )
    version: Mapped[int] = version_column()
