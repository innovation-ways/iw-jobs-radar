"""Companies, their aliases and enriched facts (document 13, section 9, ADR-025)."""

from datetime import datetime
from decimal import Decimal
from typing import Any

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
from jobs_radar.domain.enums import EmployerType, EmployerTypeOrigin, FactOrigin


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
