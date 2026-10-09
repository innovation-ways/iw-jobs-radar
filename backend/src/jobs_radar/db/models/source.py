"""Job sources, the collection schedule and collection runs (ADR-012, ADR-017, ADR-031)."""

from datetime import datetime, time
from typing import Any

from sqlalchemy import CheckConstraint, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from jobs_radar.db.base import Base, CreatedAtMixin, TimestampMixin
from jobs_radar.db.columns import (
    bool_column,
    bytes_column,
    enum_check,
    fk_column,
    int_column,
    json_column,
    pk_column,
    text_column,
    timestamp_column,
    version_column,
)
from jobs_radar.domain.enums import RunStatus, RunTrigger, SourceOutcome, SourceType


class SourceConfiguration(TimestampMixin, Base):
    """A configured job source: one company board on one ATS, managed from the frontend."""

    __tablename__ = "source_configuration"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "source_type",
            "external_identifier",
            name="uq_source_configuration_owner_type_identifier",
        ),
        enum_check("source_type", SourceType),
        CheckConstraint("rate_limit_per_minute >= 1", name="rate_limit_positive"),
        {"comment": "Configured job sources with their health-relevant settings."},
    )

    source_configuration_id: Mapped[int] = pk_column("Surrogate primary key of the source.")
    owner_id: Mapped[int] = fk_column("owner.owner_id", "Owner of the source configuration.")
    company_id: Mapped[int | None] = fk_column(
        "company.company_id", "Company the board belongs to.", nullable=True
    )
    source_type: Mapped[str] = text_column(
        "Adapter kind: an ATS company board or a job board (ADR-049, ADR-050).", length=20
    )
    external_identifier: Mapped[str] = text_column(
        "Board token or company slug on the ATS.", length=200
    )
    display_name: Mapped[str] = text_column("Name shown in the interface.", length=200)
    url: Mapped[str] = text_column("Endpoint URL used to collect the board.")
    enabled: Mapped[bool] = bool_column(
        "Whether the source takes part in collection runs.", default=True
    )
    rate_limit_per_minute: Mapped[int] = int_column(
        "Maximum requests per minute to this source.", default=6
    )
    config_json: Mapped[Any] = json_column("Adapter-specific, non-secret configuration.")
    credential_ciphertext: Mapped[bytes | None] = bytes_column(
        "Encrypted access credential, if the source needs one (write-only, ADR-033)."
    )
    credential_updated_at: Mapped[datetime | None] = timestamp_column(
        "UTC time at which the credential was last written.", nullable=True
    )
    etag: Mapped[str | None] = text_column(
        "Last ETag returned by the source, for conditional requests.", nullable=True
    )
    version: Mapped[int] = version_column()


class ScheduleSetting(TimestampMixin, Base):
    """The owner's daily collection schedule; the worker reads it without a restart (ADR-017)."""

    __tablename__ = "schedule_setting"
    __table_args__ = {"comment": "Daily collection time and time zone, one row per owner."}

    schedule_setting_id: Mapped[int] = pk_column("Surrogate primary key of the setting.")
    owner_id: Mapped[int] = fk_column("owner.owner_id", "Owner of the schedule.", unique=True)
    run_time_local: Mapped[time] = mapped_column(
        Time, nullable=False, comment="Local wall-clock time of the daily run."
    )
    timezone: Mapped[str] = text_column(
        "IANA time zone name, for example Europe/Lisbon.", length=64
    )
    enabled: Mapped[bool] = bool_column("Whether the daily run is active.", default=True)
    version: Mapped[int] = version_column()


class CollectionRun(TimestampMixin, Base):
    """One execution request for all enabled sources; status changes as the worker progresses."""

    __tablename__ = "collection_run"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "scheduled_for", name="uq_collection_run_owner_id_scheduled_for"
        ),
        enum_check("trigger", RunTrigger),
        enum_check("status", RunStatus),
        {"comment": "Collection runs, scheduled or manual."},
    )

    collection_run_id: Mapped[int] = pk_column("Surrogate primary key of the run.")
    owner_id: Mapped[int] = fk_column("owner.owner_id", "Owner the run belongs to.")
    source_configuration_id: Mapped[int | None] = fk_column(
        "source_configuration.source_configuration_id",
        "Source this run is limited to; null means all enabled sources.",
        nullable=True,
        ondelete="CASCADE",
    )
    trigger: Mapped[str] = text_column("scheduled or manual.", length=20)
    status: Mapped[str] = text_column(
        "queued, running, succeeded, partial, failed or cancelled.", length=20, default="queued"
    )
    scheduled_for: Mapped[datetime | None] = timestamp_column(
        "Planned UTC time for scheduled runs; unique per owner so a run is created once.",
        nullable=True,
    )
    requested_at: Mapped[datetime] = timestamp_column(
        "UTC time at which the run was requested.", default_now=True
    )
    started_at: Mapped[datetime | None] = timestamp_column(
        "UTC time at which execution began.", nullable=True
    )
    finished_at: Mapped[datetime | None] = timestamp_column(
        "UTC time at which execution ended.", nullable=True
    )
    error_class: Mapped[str | None] = text_column(
        "Classification of a run-level failure.", length=50, nullable=True
    )
    worker_name: Mapped[str | None] = text_column(
        "Worker that executed the run.", length=100, nullable=True
    )
    version: Mapped[int] = version_column()


class SourceRunResult(CreatedAtMixin, Base):
    """Outcome of collecting one source within one run (append-only)."""

    __tablename__ = "source_run_result"
    __table_args__ = (
        UniqueConstraint(
            "collection_run_id",
            "source_configuration_id",
            name="uq_source_run_result_run_source",
        ),
        enum_check("outcome", SourceOutcome),
        {"comment": "Per-source outcome of a collection run (append-only)."},
    )

    source_run_result_id: Mapped[int] = pk_column("Surrogate primary key of the result.")
    collection_run_id: Mapped[int] = fk_column(
        "collection_run.collection_run_id", "Run the result belongs to.", ondelete="CASCADE"
    )
    source_configuration_id: Mapped[int] = fk_column(
        "source_configuration.source_configuration_id",
        "Source that was collected.",
        ondelete="CASCADE",
    )
    started_at: Mapped[datetime] = timestamp_column(
        "UTC time at which the source collection began."
    )
    finished_at: Mapped[datetime] = timestamp_column("UTC time at which it ended.")
    outcome: Mapped[str] = text_column(
        "success, not_modified, partial, failed or skipped.", length=20
    )
    collected_count: Mapped[int] = int_column("Postings obtained from the source.", default=0)
    new_count: Mapped[int] = int_column("Postings seen for the first time.", default=0)
    updated_count: Mapped[int] = int_column("Postings that changed materially.", default=0)
    deduplicated_count: Mapped[int] = int_column("Postings recognised as already known.", default=0)
    closed_count: Mapped[int] = int_column("Postings marked closed in this run.", default=0)
    dropped_count: Mapped[int] = int_column(
        "Postings left out by the source's filters (job boards).", default=0
    )
    http_status: Mapped[int | None] = int_column(
        "HTTP status of the main request, if any.", nullable=True
    )
    error_class: Mapped[str | None] = text_column(
        "Classified failure reason.", length=50, nullable=True
    )
    error_message: Mapped[str | None] = text_column(
        "Safe human-readable failure message.", nullable=True
    )
    duration_ms: Mapped[int] = int_column("Duration of the collection in milliseconds.")
