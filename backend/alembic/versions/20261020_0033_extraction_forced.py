"""let the owner ask for an analysis the queue would otherwise skip (ADR-080, phase 6c)

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-20 21:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every existing row keeps the normal rules (not forced).
    op.add_column(
        "job_extraction",
        sa.Column(
            "forced",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment=(
                "True when the owner asked to analyse the job again: the worker then claims the "
                "row even though the job already has an accepted answer from an earlier prompt."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("job_extraction", "forced")
