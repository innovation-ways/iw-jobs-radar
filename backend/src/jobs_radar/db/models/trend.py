"""Weekly aggregates over relevant jobs for market trends (document 13, section 11, ADR-022)."""

from datetime import date, datetime

from sqlalchemy import Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from jobs_radar.db.base import Base
from jobs_radar.db.columns import (
    enum_check,
    fk_column,
    int_column,
    pk_column,
    text_column,
    timestamp_column,
)
from jobs_radar.domain.enums import TrendTermKind


class TrendWeekly(Base):
    """Counts of one term in one week, under one intent revision and taxonomy version."""

    __tablename__ = "trend_weekly"
    __table_args__ = (
        UniqueConstraint(
            "search_intent_id",
            "intent_revision_id",
            "week_start",
            "term_kind",
            "term_key",
            name="uq_trend_weekly_intent_revision_week_term",
        ),
        enum_check("term_kind", TrendTermKind),
        {"comment": "Stored weekly aggregates of relevant jobs, recomputed by the trends job."},
    )

    trend_weekly_id: Mapped[int] = pk_column("Surrogate primary key of the aggregate.")
    owner_id: Mapped[int] = fk_column(
        "owner.owner_id", "Owner the aggregate belongs to.", index=False
    )
    search_intent_id: Mapped[int] = fk_column(
        "search_intent.search_intent_id", "Intent that defined relevance.", ondelete="CASCADE"
    )
    intent_revision_id: Mapped[int] = fk_column(
        "intent_revision.intent_revision_id",
        "Intent revision used for relevance.",
        ondelete="CASCADE",
    )
    taxonomy_version_id: Mapped[int] = fk_column(
        "taxonomy_version.taxonomy_version_id", "Taxonomy version of the term keys."
    )
    week_start: Mapped[date] = mapped_column(
        Date, nullable=False, comment="Monday of the week (UTC date)."
    )
    term_kind: Mapped[str] = text_column("Kind of term counted.", length=30)
    term_key: Mapped[str] = text_column("Key of the term counted.", length=120)
    relevance_min_score: Mapped[int] = int_column(
        "Minimum fit score for a job to count as relevant."
    )
    open_count: Mapped[int] = int_column("Relevant open opportunities with the term at week end.")
    new_count: Mapped[int] = int_column("Relevant opportunities first seen in the week.")
    closed_count: Mapped[int] = int_column("Relevant opportunities closed in the week.")
    relevant_total_open: Mapped[int] = int_column(
        "All relevant open opportunities at week end (for shares)."
    )
    source_set_hash: Mapped[str] = text_column(
        "Hash of the enabled source set; changes mark non-comparable weeks.", length=64
    )
    computed_at: Mapped[datetime] = timestamp_column(
        "UTC time at which the aggregate was computed.", default_now=True
    )
