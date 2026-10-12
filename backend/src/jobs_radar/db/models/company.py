"""Companies, their aliases and enriched facts (document 13, section 9, ADR-025)."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped

from jobs_radar.db.base import Base, CreatedAtMixin, TimestampMixin
from jobs_radar.db.columns import (
    enum_check,
    fk_column,
    json_column,
    numeric_column,
    pk_column,
    text_column,
    timestamp_column,
)
from jobs_radar.domain.enums import (
    EmployerType,
    EmployerTypeOrigin,
    EnrichmentCandidateStatus,
    FactOrigin,
)


class Company(TimestampMixin, Base):
    """One real company. Source boards and postings link to it."""

    __tablename__ = "company"
    __table_args__ = (
        enum_check("employer_type", EmployerType, nullable=True),
        enum_check("employer_type_origin", EmployerTypeOrigin, nullable=True),
        {"comment": "Companies that publish jobs."},
    )

    company_id: Mapped[int] = pk_column("Surrogate primary key of the company.")
    canonical_name: Mapped[str] = text_column("Display name of the company.", length=200)
    name_normalised: Mapped[str] = text_column(
        "Lowercase name used for search and matching.", length=200, index=True
    )
    homepage_url: Mapped[str | None] = text_column("Current accepted homepage URL.", nullable=True)
    careers_url: Mapped[str | None] = text_column(
        "Current accepted careers-site URL.", nullable=True
    )
    employer_type: Mapped[str | None] = text_column(
        "Direct employer, agency or consultancy; null when not determined.",
        length=30,
        nullable=True,
    )
    employer_type_origin: Mapped[str | None] = text_column(
        "Where the employer-type classification came from.", length=20, nullable=True
    )
    enriched_at: Mapped[datetime | None] = timestamp_column(
        "UTC time of the last enrichment attempt; null if never enriched.", nullable=True
    )


class CompanyAlias(CreatedAtMixin, Base):
    """Another normalised name by which a company is known."""

    __tablename__ = "company_alias"
    __table_args__ = {"comment": "Alternative normalised names of companies."}

    company_alias_id: Mapped[int] = pk_column("Surrogate primary key of the alias.")
    company_id: Mapped[int] = fk_column(
        "company.company_id", "Company the alias belongs to.", ondelete="CASCADE"
    )
    alias_normalised: Mapped[str] = text_column("Lowercase alias.", length=200, unique=True)


class CompanyFact(CreatedAtMixin, Base):
    """A fact about a company with its source, date and licence. Superseded facts are kept."""

    __tablename__ = "company_fact"
    __table_args__ = (
        enum_check("origin", FactOrigin),
        {"comment": "Facts about companies, each with provenance."},
    )

    company_fact_id: Mapped[int] = pk_column("Surrogate primary key of the fact.")
    company_id: Mapped[int] = fk_column(
        "company.company_id", "Company the fact describes.", ondelete="CASCADE"
    )
    fact_key: Mapped[str] = text_column(
        "Kind of fact, for example homepage or employee_count.", length=60, index=True
    )
    value_json: Mapped[Any] = json_column("The fact's value.")
    origin: Mapped[str] = text_column("source, public_dataset, ai_inference or user.", length=20)
    source_name: Mapped[str] = text_column(
        "Name of the source, for example wikidata or job_board.", length=60
    )
    source_url: Mapped[str | None] = text_column("URL where the fact was obtained.", nullable=True)
    retrieved_at: Mapped[datetime] = timestamp_column("UTC time at which the fact was retrieved.")
    licence: Mapped[str | None] = text_column(
        "Licence of the source data, for example CC0.", length=60, nullable=True
    )
    confidence: Mapped[Decimal | None] = numeric_column(
        "Confidence between 0 and 1, if known.", nullable=True
    )
    superseded_at: Mapped[datetime | None] = timestamp_column(
        "UTC time at which a newer fact replaced this one; null while current.", nullable=True
    )


class CompanyEnrichmentCandidate(CreatedAtMixin, Base):
    """An entity found in a public dataset that may be the company (document 13, section 9)."""

    __tablename__ = "company_enrichment_candidate"
    __table_args__ = (
        enum_check("status", EnrichmentCandidateStatus),
        UniqueConstraint("company_id", "source_name", "external_id", name="uq_company_candidate"),
        {"comment": "Entities from public datasets proposed as the company; the owner decides."},
    )

    company_enrichment_candidate_id: Mapped[int] = pk_column(
        "Surrogate primary key of the candidate."
    )
    company_id: Mapped[int] = fk_column(
        "company.company_id", "Company the candidate may be.", ondelete="CASCADE"
    )
    source_name: Mapped[str] = text_column("Dataset the candidate came from.", length=60)
    external_id: Mapped[str] = text_column(
        "Identifier in that dataset, for example Q42.", length=120
    )
    label: Mapped[str] = text_column("Name of the entity in the dataset.", length=300)
    description: Mapped[str | None] = text_column(
        "Short description of the entity in the dataset.", nullable=True
    )
    website: Mapped[str | None] = text_column("Official website of the entity.", nullable=True)
    payload_json: Mapped[Any] = json_column(
        "Facts the candidate would add if accepted: key -> {value, source_url, licence}."
    )
    status: Mapped[str] = text_column(
        "pending until the owner or the domain rule decides.", length=20, default="pending"
    )
    decided_by: Mapped[str | None] = text_column(
        "domain_match or user, once decided.", length=20, nullable=True
    )
    decided_at: Mapped[datetime | None] = timestamp_column(
        "UTC time of the decision.", nullable=True
    )


class CompanyFollow(CreatedAtMixin, Base):
    """The owner follows a company: personal state, not a company fact (ADR-053)."""

    __tablename__ = "company_follow"
    __table_args__ = (
        UniqueConstraint("owner_id", "company_id", name="uq_company_follow_owner_id_company_id"),
        {"comment": "Companies an owner follows; unfollowing deletes the row."},
    )

    company_follow_id: Mapped[int] = pk_column("Surrogate primary key of the follow.")
    owner_id: Mapped[int] = fk_column("owner.owner_id", "Owner who follows.", index=False)
    company_id: Mapped[int] = fk_column(
        "company.company_id", "Company that is followed.", ondelete="CASCADE"
    )


class CompanyIgnore(CreatedAtMixin, Base):
    """The owner ignores a company: its offers go to Ignored (personal state, ADR-061)."""

    __tablename__ = "company_ignore"
    __table_args__ = (
        UniqueConstraint("owner_id", "company_id", name="uq_company_ignore_owner_id_company_id"),
        {"comment": "Companies an owner ignores; undoing deletes the row."},
    )

    company_ignore_id: Mapped[int] = pk_column("Surrogate primary key of the ignore.")
    owner_id: Mapped[int] = fk_column("owner.owner_id", "Owner who ignores.", index=False)
    company_id: Mapped[int] = fk_column(
        "company.company_id", "Company that is ignored.", ondelete="CASCADE"
    )
