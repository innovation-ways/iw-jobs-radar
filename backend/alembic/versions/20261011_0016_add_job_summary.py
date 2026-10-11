"""add the model-written job summaries (ADR-059)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-11 15:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

from jobs_radar.db.triggers import create_append_only_trigger, drop_append_only_trigger

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_summary",
        sa.Column(
            "job_summary_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
            comment="Surrogate primary key of the summary.",
        ),
        sa.Column(
            "job_snapshot_id",
            sa.BigInteger(),
            nullable=False,
            comment="Snapshot that was summarised.",
        ),
        sa.Column("provider", sa.String(length=50), nullable=False, comment="AI provider kind."),
        sa.Column("model", sa.String(length=100), nullable=False, comment="AI model identifier."),
        sa.Column(
            "prompt_version",
            sa.String(length=50),
            nullable=False,
            comment="Prompt template version, for example summary-v1.",
        ),
        sa.Column("status", sa.String(length=20), nullable=False, comment="succeeded or failed."),
        sa.Column(
            "summary_text",
            sa.Text(),
            nullable=True,
            comment="The summary (one or two paragraphs in English); null when the attempt failed.",
        ),
        sa.Column(
            "error_class",
            sa.String(length=50),
            nullable=True,
            comment="Classified failure reason when the attempt failed.",
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
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')", name=op.f("ck_job_summary_status_valid")
        ),
        sa.CheckConstraint(
            "status <> 'succeeded' OR summary_text IS NOT NULL",
            name=op.f("ck_job_summary_success_has_text"),
        ),
        sa.ForeignKeyConstraint(
            ["job_snapshot_id"],
            ["job_snapshot.job_snapshot_id"],
            name=op.f("fk_job_summary_job_snapshot_id_job_snapshot"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_summary_id", name=op.f("pk_job_summary")),
        comment="Model-written summaries of job snapshots (append-only, ADR-059).",
    )
    op.create_index(op.f("ix_job_summary_job_snapshot_id"), "job_summary", ["job_snapshot_id"])
    op.create_index(
        "uq_job_summary_inputs",
        "job_summary",
        ["job_snapshot_id", "provider", "model", "prompt_version"],
        unique=True,
        postgresql_where=sa.text("status = 'succeeded'"),
    )
    op.execute(create_append_only_trigger("job_summary"))


def downgrade() -> None:
    op.execute(drop_append_only_trigger("job_summary"))
    op.drop_index("uq_job_summary_inputs", table_name="job_summary")
    op.drop_index(op.f("ix_job_summary_job_snapshot_id"), table_name="job_summary")
    op.drop_table("job_summary")
