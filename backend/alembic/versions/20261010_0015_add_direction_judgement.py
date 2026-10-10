"""add the career-direction judgements and the direction basis of evaluations (ADR-057)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-10 22:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

from jobs_radar.db.triggers import create_append_only_trigger, drop_append_only_trigger

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_UNIQUE = "uq_match_evaluation_inputs"
_KEYS = ["job_snapshot_id", "job_extraction_id", "profile_revision_id", "intent_revision_id"]


def upgrade() -> None:
    op.create_table(
        "direction_judgement",
        sa.Column(
            "direction_judgement_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
            comment="Surrogate primary key of the judgement.",
        ),
        sa.Column(
            "job_snapshot_id", sa.BigInteger(), nullable=False, comment="Snapshot that was judged."
        ),
        sa.Column(
            "direction_hash",
            sa.String(length=71),
            nullable=False,
            comment="SHA-256 of the direction text that was judged, so a changed text is judged again.",
        ),
        sa.Column(
            "direction_label",
            sa.String(length=60),
            nullable=False,
            comment="Label of the direction when it was judged, shown as the winning direction.",
        ),
        sa.Column("provider", sa.String(length=50), nullable=False, comment="AI provider kind."),
        sa.Column("model", sa.String(length=100), nullable=False, comment="AI model identifier."),
        sa.Column(
            "prompt_version",
            sa.String(length=50),
            nullable=False,
            comment="Prompt template version, for example direction-v1.",
        ),
        sa.Column(
            "level",
            sa.String(length=20),
            nullable=False,
            comment="strong, partial, weak, none or unknown.",
        ),
        sa.Column(
            "job_quote",
            sa.Text(),
            nullable=True,
            comment="Verbatim quote from the posting that supports the level.",
        ),
        sa.Column(
            "direction_quote",
            sa.Text(),
            nullable=True,
            comment="Verbatim quote from the direction text that the posting matches.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="UTC timestamp at which the row was created.",
        ),
        sa.CheckConstraint(
            "level IN ('strong', 'partial', 'weak', 'none', 'unknown')",
            name=op.f("ck_direction_judgement_level_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["job_snapshot_id"],
            ["job_snapshot.job_snapshot_id"],
            name=op.f("fk_direction_judgement_job_snapshot_id_job_snapshot"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("direction_judgement_id", name=op.f("pk_direction_judgement")),
        sa.UniqueConstraint(
            "job_snapshot_id",
            "direction_hash",
            "provider",
            "model",
            "prompt_version",
            name="uq_direction_judgement_inputs",
        ),
        comment="Model judgements of a job against the owner's career directions (ADR-057).",
    )
    op.create_index(
        op.f("ix_direction_judgement_job_snapshot_id"), "direction_judgement", ["job_snapshot_id"]
    )
    op.execute(create_append_only_trigger("direction_judgement"))

    op.add_column(
        "match_evaluation",
        sa.Column(
            "direction_basis",
            sa.String(length=71),
            server_default="none",
            nullable=False,
            comment="none, or the hash of the direction judgements the score used (ADR-057).",
        ),
    )
    op.drop_constraint(_UNIQUE, "match_evaluation", type_="unique")
    op.create_unique_constraint(
        _UNIQUE, "match_evaluation", [*_KEYS, "policy_version", "direction_basis"]
    )


def downgrade() -> None:
    # Evaluations that used judgements cannot exist without them; they are removed (with their
    # dimensions) through the audited bypass of the append-only triggers.
    op.execute("SET LOCAL jobs_radar.allow_mutation = 'on'")
    op.execute("DELETE FROM match_evaluation WHERE direction_basis <> 'none'")
    op.drop_constraint(_UNIQUE, "match_evaluation", type_="unique")
    op.create_unique_constraint(_UNIQUE, "match_evaluation", [*_KEYS, "policy_version"])
    op.drop_column("match_evaluation", "direction_basis")
    op.execute(drop_append_only_trigger("direction_judgement"))
    op.drop_index(op.f("ix_direction_judgement_job_snapshot_id"), table_name="direction_judgement")
    op.drop_table("direction_judgement")
