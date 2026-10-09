"""add extraction failure detail

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-09 13:30:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_extraction",
        sa.Column(
            "failure_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Size and last characters of the unusable answer of the latest failed attempt, "
                "so the failure can be diagnosed."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("job_extraction", "failure_json")
