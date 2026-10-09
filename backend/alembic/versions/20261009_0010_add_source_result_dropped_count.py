"""add dropped count to source run results

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-09 20:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_run_result",
        sa.Column(
            "dropped_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Postings left out by the source's filters (job boards).",
        ),
    )


def downgrade() -> None:
    op.drop_column("source_run_result", "dropped_count")
