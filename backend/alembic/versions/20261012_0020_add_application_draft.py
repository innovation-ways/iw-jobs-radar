"""add the model-written pre-application drafts (ADR-064)

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-12 20:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from jobs_radar.db.triggers import create_append_only_trigger, drop_append_only_trigger

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_draft",
        sa.Column(
            "application_draft_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
            comment="Surrogate primary key of the draft.",
        ),
        sa.Column(
            "job_snapshot_id",
            sa.BigInteger(),
            nullable=False,
            comment="Snapshot the draft was written for.",
        ),
        sa.Column(
            "profile_revision_id",
            sa.BigInteger(),
            nullable=False,
            comment="Profile revision whose facts the draft used.",
        ),
        sa.Column("provider", sa.String(length=50), nullable=False, comment="AI provider kind."),
        sa.Column("model", sa.String(length=100), nullable=False, comment="AI model identifier."),
        sa.Column(
            "prompt_version",
            sa.String(length=50),
            nullable=False,
            comment="Prompt template version, for example application-v1.",
        ),
        sa.Column(
            "draft_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Strengths, positioning, gaps and cover letter, validated with a schema_version.",
        ),
        sa.Column(
            "latency_ms",
            sa.Integer(),
            nullable=True,
            comment="Duration of the model calls in milliseconds.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="UTC timestamp at which the row was created.",
        ),
        sa.ForeignKeyConstraint(
            ["job_snapshot_id"],
            ["job_snapshot.job_snapshot_id"],
            name=op.f("fk_application_draft_job_snapshot_id_job_snapshot"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_revision_id"],
            ["profile_revision.profile_revision_id"],
            name=op.f("fk_application_draft_profile_revision_id_profile_revision"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("application_draft_id", name=op.f("pk_application_draft")),
        comment="Model-written pre-application drafts of jobs (append-only, ADR-064).",
    )
    op.create_index(
        op.f("ix_application_draft_job_snapshot_id"), "application_draft", ["job_snapshot_id"]
    )
    op.create_index(
        op.f("ix_application_draft_profile_revision_id"),
        "application_draft",
        ["profile_revision_id"],
    )
    op.execute(create_append_only_trigger("application_draft"))


def downgrade() -> None:
    op.execute(drop_append_only_trigger("application_draft"))
    op.drop_index(op.f("ix_application_draft_profile_revision_id"), table_name="application_draft")
    op.drop_index(op.f("ix_application_draft_job_snapshot_id"), table_name="application_draft")
    op.drop_table("application_draft")
