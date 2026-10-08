"""Skills, their aliases, judged relations and review candidates (document 13, section 2.2)."""

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped

from jobs_radar.db.base import Base, CreatedAtMixin, TimestampMixin
from jobs_radar.db.columns import enum_check, fk_column, pk_column, text_column
from jobs_radar.domain.enums import CandidateStatus, JudgementOrigin, SkillKind, SkillRelationKind


class Skill(TimestampMixin, Base):
    """A canonical skill, created on demand from profiles and job extractions."""

    __tablename__ = "skill"
    __table_args__ = (
        enum_check("kind", SkillKind),
        {"comment": "Canonical skills referenced by profiles and job extractions."},
    )

    skill_id: Mapped[int] = pk_column("Surrogate primary key of the skill.")
    canonical_name: Mapped[str] = text_column(
        "Canonical display name of the skill.", length=120, unique=True
    )
    kind: Mapped[str] = text_column("Category: technology, domain knowledge or method.", length=30)
    esco_uri: Mapped[str | None] = text_column(
        "Optional ESCO concept URI (mapping is a deferred improvement).", nullable=True
    )


class SkillAlias(CreatedAtMixin, Base):
    """A normalised spelling that resolves to a skill (for example ``node js``)."""

    __tablename__ = "skill_alias"
    __table_args__ = {"comment": "Normalised spellings that map a mention to a skill."}

    skill_alias_id: Mapped[int] = pk_column("Surrogate primary key of the alias.")
    skill_id: Mapped[int] = fk_column(
        "skill.skill_id", "Skill the alias resolves to.", ondelete="CASCADE"
    )
    alias_normalised: Mapped[str] = text_column(
        "Lowercase alias with punctuation stripped.", length=120, unique=True
    )


class SkillRelation(CreatedAtMixin, Base):
    """Cached judgement of how two skills relate. Stored once per pair with ``a < b``."""

    __tablename__ = "skill_relation"
    __table_args__ = (
        UniqueConstraint(
            "skill_id_a", "skill_id_b", name="uq_skill_relation_skill_id_a_skill_id_b"
        ),
        CheckConstraint("skill_id_a < skill_id_b", name="ordered_pair"),
        enum_check("relation", SkillRelationKind),
        enum_check("origin", JudgementOrigin),
        {"comment": "Cached equivalent/related/unrelated judgements for skill pairs."},
    )

    skill_relation_id: Mapped[int] = pk_column("Surrogate primary key of the relation.")
    skill_id_a: Mapped[int] = fk_column(
        "skill.skill_id", "Lower-numbered skill of the pair.", ondelete="CASCADE"
    )
    skill_id_b: Mapped[int] = fk_column(
        "skill.skill_id", "Higher-numbered skill of the pair.", ondelete="CASCADE"
    )
    relation: Mapped[str] = text_column(
        "Judged relation: equivalent, related or unrelated.", length=20
    )
    origin: Mapped[str] = text_column("Who judged: the AI or the user.", length=10)
    provider: Mapped[str | None] = text_column(
        "AI provider that produced the judgement.", length=50, nullable=True
    )
    model: Mapped[str | None] = text_column(
        "AI model that produced the judgement.", length=100, nullable=True
    )
    prompt_version: Mapped[str | None] = text_column(
        "Prompt template version used.", length=50, nullable=True
    )


class SkillCandidate(TimestampMixin, Base):
    """A skill mention the extractor could not map; awaits automatic or manual acceptance."""

    __tablename__ = "skill_candidate"
    __table_args__ = (
        enum_check("status", CandidateStatus),
        {"comment": "Proposed new skills awaiting review."},
    )

    skill_candidate_id: Mapped[int] = pk_column("Surrogate primary key of the candidate.")
    proposed_canonical_name: Mapped[str] = text_column(
        "Canonical name proposed by the extractor.", length=120
    )
    alias_normalised: Mapped[str] = text_column(
        "Normalised mention that triggered the proposal.", length=120, index=True
    )
    status: Mapped[str] = text_column(
        "Review state: pending, accepted or rejected.", length=20, default="pending"
    )
    skill_id: Mapped[int | None] = fk_column(
        "skill.skill_id", "Skill created or matched when the candidate was accepted.", nullable=True
    )
