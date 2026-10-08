"""Baseline: worker heartbeat table and the append-only trigger function.

Revision ID: 0001
Revises:
Create Date: 2026-10-08
"""

import sqlalchemy as sa
from alembic import op

from jobs_radar.db.triggers import DROP_FORBID_MUTATION_FUNCTION, FORBID_MUTATION_FUNCTION

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the heartbeat table and the reusable trigger function (ADR-030, ADR-031)."""
    op.create_table(
        "worker_heartbeat",
        sa.Column(
            "worker_heartbeat_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
            comment="Surrogate primary key of the heartbeat row.",
        ),
        sa.Column(
            "worker_name",
            sa.String(length=100),
            nullable=False,
            comment="Logical name of the worker process that owns this heartbeat.",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="UTC time at which the current worker process started.",
        ),
        sa.Column(
            "beat_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="UTC time of the most recent heartbeat.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="UTC timestamp at which the row was created.",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="UTC timestamp of the last modification of the row.",
        ),
        sa.PrimaryKeyConstraint("worker_heartbeat_id", name=op.f("pk_worker_heartbeat")),
        sa.UniqueConstraint("worker_name", name=op.f("uq_worker_heartbeat_worker_name")),
        comment="Liveness of worker processes, refreshed every loop iteration.",
    )
    op.execute(FORBID_MUTATION_FUNCTION)


def downgrade() -> None:
    """Remove everything created by ``upgrade``."""
    op.execute(DROP_FORBID_MUTATION_FUNCTION)
    op.drop_table("worker_heartbeat")
