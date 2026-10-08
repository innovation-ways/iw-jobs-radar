"""Deterministic evaluations of a job against a profile and an intent (document 13, section 8)."""

from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped

from jobs_radar.db.base import Base, CreatedAtMixin
from jobs_radar.db.columns import (
    bool_column,
    enum_check,
    fk_column,
    int_column,
    json_column,
    numeric_column,
    pk_column,
    text_column,
)
from jobs_radar.domain.enums import MatchQuality, Recommendation, ScoreStatus


class MatchEvaluation(CreatedAtMixin, Base):
    """The immutable result of scoring one snapshot under exact profile and intent revisions."""

    __tablename__ = "match_evaluation"
    __table_args__ = (
        UniqueConstraint(
            "job_snapshot_id",
            "job_extraction_id",
            "profile_revision_id",
            "intent_revision_id",
            "policy_version",
            name="uq_match_evaluation_inputs",
        ),
        enum_check("recommendation", Recommendation),
        CheckConstraint("fit_score >= 0 AND fit_score <= 100", name="fit_score_range"),
        {"comment": "Immutable, reproducible evaluations (append-only)."},
    )

    match_evaluation_id: Mapped[int] = pk_column("Surrogate primary key of the evaluation.")
    job_snapshot_id: Mapped[int] = fk_column(
        "job_snapshot.job_snapshot_id", "Snapshot that was scored."
    )
    job_extraction_id: Mapped[int] = fk_column(
        "job_extraction.job_extraction_id", "Extraction the score used."
    )
    profile_revision_id: Mapped[int] = fk_column(
        "profile_revision.profile_revision_id", "Profile revision used.", ondelete="CASCADE"
    )
    intent_revision_id: Mapped[int] = fk_column(
        "intent_revision.intent_revision_id", "Intent revision used.", ondelete="CASCADE"
    )
    policy_version: Mapped[str] = text_column(
        "Matching policy version, for example matching-v1.", length=50
    )
    job_source_hash: Mapped[str] = text_column(
        "Content hash of the scored snapshot, for traceability.", length=71
    )
    fit_score: Mapped[int] = int_column("Final score from 0 to 100.")
    recommendation: Mapped[str] = text_column(
        "recommended or not_recommended (a hard gate fired).", length=20
    )
    gates_json: Mapped[Any] = json_column("Fired gates with reasons and evidence.")
    weights_json: Mapped[Any] = json_column("Weights that applied to the evaluation.")


class ScoreDimension(CreatedAtMixin, Base):
    """One scored dimension with its status, strength, contribution and evidence (append-only)."""

    __tablename__ = "score_dimension"
    __table_args__ = (
        UniqueConstraint(
            "match_evaluation_id",
            "dimension_key",
            name="uq_score_dimension_match_evaluation_id_dimension_key",
        ),
        enum_check("status", ScoreStatus),
        enum_check("quality", MatchQuality, nullable=True),
        CheckConstraint("strength >= 0 AND strength <= 1", name="strength_range"),
        {"comment": "Dimension-level detail of an evaluation (append-only)."},
    )

    score_dimension_id: Mapped[int] = pk_column("Surrogate primary key of the dimension row.")
    match_evaluation_id: Mapped[int] = fk_column(
        "match_evaluation.match_evaluation_id", "Evaluation the row belongs to.", ondelete="CASCADE"
    )
    dimension_key: Mapped[str] = text_column(
        "Dimension identifier, for example skills_technology.", length=50
    )
    status: Mapped[str] = text_column("match, mismatch or unknown.", length=20)
    quality: Mapped[str | None] = text_column(
        "strong, partial or weak for matches; otherwise null.", length=20, nullable=True
    )
    weight: Mapped[int] = int_column("Raw weight set by the owner (0 to 40).")
    effective_weight: Mapped[Decimal] = numeric_column(
        "Weight normalised to a 100-point scale.", precision=7, scale=4
    )
    strength: Mapped[Decimal] = numeric_column("Strength from 0 to 1.")
    contribution: Mapped[Decimal] = numeric_column(
        "Points contributed to the score.", precision=7, scale=4
    )
    excluded: Mapped[bool] = bool_column(
        "True when the weight is 0 and the dimension is excluded.", default=False
    )
    evidence_json: Mapped[Any] = json_column(
        "Evidence: job quote, profile fact or option compared."
    )
    explanation: Mapped[str] = text_column("One-sentence explanation shown to the owner.")
