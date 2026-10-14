"""raise the default of the inbox low-fit floor from 20 to 30 (ADR-071)

Only the column default changes: rows that already exist keep the value the owner has.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-14 10:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "schedule_setting",
        "set_aside_below_fit",
        server_default=sa.text("30"),
        existing_type=sa.Integer(),
    )


def downgrade() -> None:
    op.alter_column(
        "schedule_setting",
        "set_aside_below_fit",
        server_default=sa.text("20"),
        existing_type=sa.Integer(),
    )
