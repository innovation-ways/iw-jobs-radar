"""Jobs: postings, immutable snapshots, change events, AI extractions and opportunities."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped

from jobs_radar.db.base import Base, CreatedAtMixin, TimestampMixin
from jobs_radar.db.columns import (
    bool_column,
    enum_check,
    fk_column,
    int_column,
    json_column,
    numeric_column,
    pk_column,
    text_column,
    timestamp_column,
)
from jobs_radar.domain.enums import JobExtractionStatus, LinkState


class JobPosting(TimestampMixin, Base):
    """One listing on one source. It holds source facts only: no user workflow state (ADR-006)."""

    __tablename__ = "job_posting"
    __table_args__ = (
        UniqueConstraint(
            "source_configuration_id",
            "external_job_id",
            name="uq_job_posting_source_configuration_id_external_job_id",
        ),
        {"comment": "Listings found on sources; source-authoritative facts."},
    )

    job_posting_id: Mapped[int] = pk_column("Surrogate primary key of the posting.")
    source_configuration_id: Mapped[int] = fk_column(
        "source_configuration.source_configuration_id", "Source the posting was found on."
    )
    company_id: Mapped[int] = fk_column("company.company_id", "Company that published the posting.")
    external_job_id: Mapped[str] = text_column(
        "Identifier of the posting on the source.", length=200
    )
    source_type: Mapped[str] = text_column("Kind of source the posting came from.", length=20)
    source_url: Mapped[str] = text_column("Original posting URL (provenance).")
    title: Mapped[str] = text_column("Latest title of the posting.", length=500)
    current_content_hash: Mapped[str] = text_column(
        "Hash of the latest snapshot's content.", length=71
    )
    first_seen_at: Mapped[datetime] = timestamp_column(
        "UTC time at which the posting first appeared.", index=True
    )
    last_seen_at: Mapped[datetime] = timestamp_column(
        "UTC time of the latest run that still listed it."
    )
    closed_at: Mapped[datetime | None] = timestamp_column(
        "UTC time at which the posting was marked closed; null while open.",
        nullable=True,
        index=True,
    )


class JobSnapshot(CreatedAtMixin, Base):
    """An immutable capture of a posting's content, used for change detection (append-only)."""

    __tablename__ = "job_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "job_posting_id", "content_hash", name="uq_job_snapshot_job_posting_id_content_hash"
        ),
        Index("ix_job_snapshot_job_posting_id_fetched_at", "job_posting_id", "fetched_at"),
        {"comment": "Immutable captures of posting content (append-only)."},
    )

    job_snapshot_id: Mapped[int] = pk_column("Surrogate primary key of the snapshot.")
    job_posting_id: Mapped[int] = fk_column(
        "job_posting.job_posting_id", "Posting the snapshot captures.", index=False
    )
    content_hash: Mapped[str] = text_column(
        "Hash of the normalised content (sha256:...).", length=71
    )
    fetched_at: Mapped[datetime] = timestamp_column("UTC time at which the content was fetched.")
    raw_payload_json: Mapped[Any] = json_column("Payload exactly as returned by the source.")
    normalised_json: Mapped[Any] = json_column("Normalised job (document 13, section 5).")


class JobChangeEvent(CreatedAtMixin, Base):
    """Records which fields changed between two snapshots and whether the change was material."""

    __tablename__ = "job_change_event"
    __table_args__ = {"comment": "Changes detected between consecutive snapshots (append-only)."}

    job_change_event_id: Mapped[int] = pk_column("Surrogate primary key of the event.")
    job_posting_id: Mapped[int] = fk_column("job_posting.job_posting_id", "Posting that changed.")
    from_job_snapshot_id: Mapped[int | None] = fk_column(
        "job_snapshot.job_snapshot_id", "Earlier snapshot; null for the first one.", nullable=True
    )
    to_job_snapshot_id: Mapped[int] = fk_column("job_snapshot.job_snapshot_id", "Later snapshot.")
    changed_fields: Mapped[Any] = json_column("List of changed field names.")
    is_material: Mapped[bool] = bool_column(
        "True when the change can return a reviewed job to attention (LLD section 5).",
        default=False,
    )


class JobExtraction(CreatedAtMixin, Base):
    """AI extraction of a snapshot. Queued as pending; immutable once succeeded or failed."""

    __tablename__ = "job_extraction"
    __table_args__ = (
        UniqueConstraint(
            "job_snapshot_id",
            "provider",
            "model",
            "prompt_version",
            "taxonomy_version_id",
            name="uq_job_extraction_snapshot_provider_model_prompt_taxonomy",
        ),
        enum_check("status", JobExtractionStatus),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        {"comment": "AI attribute extractions per job snapshot (immutable once finalised)."},
    )

    job_extraction_id: Mapped[int] = pk_column("Surrogate primary key of the extraction.")
    job_snapshot_id: Mapped[int] = fk_column(
        "job_snapshot.job_snapshot_id", "Snapshot the extraction describes."
    )
    status: Mapped[str] = text_column("pending, succeeded or failed.", length=20, default="pending")
    provider: Mapped[str] = text_column("AI provider kind.", length=50)
    model: Mapped[str] = text_column("AI model identifier.", length=100)
    prompt_version: Mapped[str] = text_column(
        "Prompt template version, for example extract-v1.", length=50
    )
    taxonomy_version_id: Mapped[int] = fk_column(
        "taxonomy_version.taxonomy_version_id", "Taxonomy version used during extraction."
    )
    truncated: Mapped[bool] = bool_column(
        "True when the description was truncated before extraction.", default=False
    )
    attributes_json: Mapped[Any | None] = json_column(
        "Extracted attributes with evidence.", nullable=True
    )
    error_class: Mapped[str | None] = text_column(
        "Classified failure reason.", length=50, nullable=True
    )
    attempts: Mapped[int] = int_column("Number of attempts made so far.", default=0)
    latency_ms: Mapped[int | None] = int_column(
        "Duration of the last attempt in milliseconds.", nullable=True
    )
    claimed_at: Mapped[datetime | None] = timestamp_column(
        "UTC time at which a worker claimed the task.", nullable=True
    )
    completed_at: Mapped[datetime | None] = timestamp_column(
        "UTC time at which the extraction was finalised.", nullable=True
    )


class JobOpportunity(TimestampMixin, Base):
    """One real opportunity, possibly listed on several sources (ADR-023)."""

    __tablename__ = "job_opportunity"
    __table_args__ = {"comment": "Real opportunities grouping source listings."}

    job_opportunity_id: Mapped[int] = pk_column("Surrogate primary key of the opportunity.")
    company_id: Mapped[int] = fk_column("company.company_id", "Company offering the opportunity.")
    primary_job_posting_id: Mapped[int] = fk_column(
        "job_posting.job_posting_id", "Posting treated as the primary listing."
    )
    first_seen_at: Mapped[datetime] = timestamp_column(
        "UTC time at which any listing first appeared.", index=True
    )
    last_seen_at: Mapped[datetime] = timestamp_column("UTC time of the latest run that listed it.")
    closed_at: Mapped[datetime | None] = timestamp_column(
        "UTC time at which every listing was closed; null while any is open.", nullable=True
    )


class JobOpportunityLink(TimestampMixin, Base):
    """Reversible link between a posting and an opportunity. Never destructive (ADR-023)."""

    __tablename__ = "job_opportunity_link"
    __table_args__ = (
        UniqueConstraint(
            "job_opportunity_id",
            "job_posting_id",
            name="uq_job_opportunity_link_job_opportunity_id_job_posting_id",
        ),
        # A posting belongs to at most one opportunity at a time; rejected pairs stay as history.
        Index(
            "uq_job_opportunity_link_active_posting",
            "job_posting_id",
            unique=True,
            postgresql_where=text("state <> 'rejected'"),
        ),
        enum_check("state", LinkState),
        CheckConstraint("similarity >= 0 AND similarity <= 1", name="similarity_range"),
        {"comment": "Links between postings and opportunities (similarity, decision state)."},
    )

    job_opportunity_link_id: Mapped[int] = pk_column("Surrogate primary key of the link.")
    job_opportunity_id: Mapped[int] = fk_column(
        "job_opportunity.job_opportunity_id", "Opportunity linked to."
    )
    job_posting_id: Mapped[int] = fk_column(
        "job_posting.job_posting_id", "Posting linked.", index=False
    )
    state: Mapped[str] = text_column("auto, possible, confirmed or rejected.", length=20)
    similarity: Mapped[Decimal] = numeric_column("Similarity score between 0 and 1.")
    features_json: Mapped[Any] = json_column("Similarity features used for the decision.")
    method: Mapped[str] = text_column(
        "Policy that produced the link, for example dedup-v1.", length=50
    )
    decided_by_user_at: Mapped[datetime | None] = timestamp_column(
        "UTC time of the owner's confirmation or rejection.", nullable=True
    )
