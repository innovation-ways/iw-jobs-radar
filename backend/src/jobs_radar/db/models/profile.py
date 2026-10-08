"""Career profiles, immutable revisions, evidence, uploaded-document metadata and proposals."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped

from jobs_radar.db.base import Base, CreatedAtMixin, TimestampMixin
from jobs_radar.db.columns import (
    enum_check,
    fk_column,
    int_column,
    json_column,
    numeric_column,
    pk_column,
    text_column,
    timestamp_column,
    version_column,
)
from jobs_radar.domain.enums import (
    DocumentExtractionStatus,
    EvidenceOrigin,
    ProposalItemStatus,
    ProposalStatus,
    Visibility,
)


class Document(TimestampMixin, Base):
    """Metadata of an uploaded document. The bytes are never stored (ADR-010)."""

    __tablename__ = "document"
    __table_args__ = (
        enum_check("extraction_status", DocumentExtractionStatus),
        {"comment": "Metadata of uploaded documents; original bytes are never persisted."},
    )

    document_id: Mapped[int] = pk_column("Surrogate primary key of the document.")
    owner_id: Mapped[int] = fk_column("owner.owner_id", "Owner of the document.")
    sha256: Mapped[str] = text_column(
        "SHA-256 of the uploaded bytes, for traceability.", length=64, index=True
    )
    mime_type: Mapped[str] = text_column("Detected MIME type.", length=100)
    byte_size: Mapped[int] = int_column("Size of the upload in bytes.")
    extraction_status: Mapped[str] = text_column(
        "uploaded, extracted, needs_ocr or failed.", length=20
    )
    extraction_version: Mapped[str | None] = text_column(
        "Version of the text extractor used.", length=50, nullable=True
    )


class CareerProfile(TimestampMixin, Base):
    """A named career profile; its facts live in append-only revisions."""

    __tablename__ = "career_profile"
    __table_args__ = (
        enum_check("visibility", Visibility),
        {"comment": "Named career profiles owned by a person."},
    )

    career_profile_id: Mapped[int] = pk_column("Surrogate primary key of the profile.")
    owner_id: Mapped[int] = fk_column("owner.owner_id", "Owner of the profile.")
    title: Mapped[str] = text_column("Profile name chosen by the owner.", length=120)
    visibility: Mapped[str] = text_column(
        "Visibility of the profile.", length=20, default="private"
    )
    current_profile_revision_id: Mapped[int | None] = fk_column(
        "profile_revision.profile_revision_id",
        "Latest revision; null until the first revision is created.",
        nullable=True,
        use_alter=True,
        name="fk_career_profile_current_profile_revision",
    )
    version: Mapped[int] = version_column()


class ProfileRevision(CreatedAtMixin, Base):
    """An immutable snapshot of the profile's facts (append-only, ADR-030)."""

    __tablename__ = "profile_revision"
    __table_args__ = (
        UniqueConstraint(
            "career_profile_id",
            "revision_number",
            name="uq_profile_revision_career_profile_id_revision_number",
        ),
        CheckConstraint("revision_number >= 1", name="revision_number_positive"),
        {"comment": "Immutable profile revisions (append-only)."},
    )

    profile_revision_id: Mapped[int] = pk_column("Surrogate primary key of the revision.")
    career_profile_id: Mapped[int] = fk_column(
        "career_profile.career_profile_id", "Profile the revision belongs to.", ondelete="CASCADE"
    )
    revision_number: Mapped[int] = int_column("1-based sequence number within the profile.")
    facts_json: Mapped[Any] = json_column("Profile facts (document 13, section 3).")
    privacy_json: Mapped[Any] = json_column("Privacy settings that applied to the revision.")
    change_summary: Mapped[str | None] = text_column(
        "Short description of what changed.", nullable=True
    )


class Evidence(CreatedAtMixin, Base):
    """Where an accepted profile fact came from (append-only)."""

    __tablename__ = "evidence"
    __table_args__ = (
        enum_check("origin", EvidenceOrigin),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"
        ),
        {"comment": "Provenance of accepted profile facts (append-only)."},
    )

    evidence_id: Mapped[int] = pk_column("Surrogate primary key of the evidence.")
    owner_id: Mapped[int] = fk_column("owner.owner_id", "Owner of the evidence.")
    origin: Mapped[str] = text_column("document, llm, manual or import.", length=20)
    document_id: Mapped[int | None] = fk_column(
        "document.document_id", "Source document, if any.", nullable=True, ondelete="SET NULL"
    )
    excerpt: Mapped[str | None] = text_column(
        "Short reviewed excerpt supporting the fact.", nullable=True
    )
    confidence: Mapped[Decimal | None] = numeric_column(
        "Extraction confidence between 0 and 1.", nullable=True
    )
    accepted_at: Mapped[datetime] = timestamp_column(
        "UTC time at which the owner accepted the fact."
    )


class ProfileProposal(TimestampMixin, Base):
    """A set of AI-proposed profile items awaiting review. Items are not facts until accepted."""

    __tablename__ = "profile_proposal"
    __table_args__ = (
        enum_check("status", ProposalStatus),
        {"comment": "Reviewable proposals produced from an imported document."},
    )

    profile_proposal_id: Mapped[int] = pk_column("Surrogate primary key of the proposal.")
    owner_id: Mapped[int] = fk_column("owner.owner_id", "Owner of the proposal.")
    career_profile_id: Mapped[int] = fk_column(
        "career_profile.career_profile_id", "Profile the proposal would extend.", ondelete="CASCADE"
    )
    document_id: Mapped[int | None] = fk_column(
        "document.document_id",
        "Document the proposal was generated from.",
        nullable=True,
        ondelete="SET NULL",
    )
    provider_type: Mapped[str | None] = text_column(
        "Provider kind that produced it, if any.", length=20, nullable=True
    )
    provider_model: Mapped[str | None] = text_column(
        "Model that produced it, if any.", length=100, nullable=True
    )
    prompt_version: Mapped[str | None] = text_column(
        "Prompt template version used.", length=50, nullable=True
    )
    redaction_policy: Mapped[str | None] = text_column(
        "Redaction policy applied before processing.", length=50, nullable=True
    )
    status: Mapped[str] = text_column(
        "pending until the review is applied, then completed.", length=20, default="pending"
    )
    completed_at: Mapped[datetime | None] = timestamp_column(
        "UTC time at which the review was applied.", nullable=True
    )
    version: Mapped[int] = version_column()


class ProposalItem(TimestampMixin, Base):
    """One proposed fact and the owner's review decision."""

    __tablename__ = "proposal_item"
    __table_args__ = (
        enum_check("review_status", ProposalItemStatus),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"
        ),
        {"comment": "Individual proposed profile items with their review state."},
    )

    proposal_item_id: Mapped[int] = pk_column("Surrogate primary key of the item.")
    profile_proposal_id: Mapped[int] = fk_column(
        "profile_proposal.profile_proposal_id", "Proposal the item belongs to.", ondelete="CASCADE"
    )
    path: Mapped[str] = text_column(
        "Location of the fact in the profile, for example skills or experience.", length=120
    )
    value_json: Mapped[Any] = json_column("The proposed value.")
    source_excerpt: Mapped[str | None] = text_column(
        "Excerpt of the document supporting the proposal.", nullable=True
    )
    confidence: Mapped[Decimal | None] = numeric_column(
        "Extractor confidence between 0 and 1.", nullable=True
    )
    review_status: Mapped[str] = text_column(
        "pending, accepted, edited, rejected or deferred.", length=20, default="pending"
    )
    edited_value_json: Mapped[Any | None] = json_column(
        "Value after the owner's edit, if edited.", nullable=True
    )
    evidence_id: Mapped[int | None] = fk_column(
        "evidence.evidence_id",
        "Evidence created when the item was accepted.",
        nullable=True,
        ondelete="SET NULL",
    )
    reviewed_at: Mapped[datetime | None] = timestamp_column(
        "UTC time of the decision.", nullable=True
    )
