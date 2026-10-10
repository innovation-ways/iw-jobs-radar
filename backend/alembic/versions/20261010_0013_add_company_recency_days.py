"""add the company recency limit to the schedule setting (ADR-053)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-10 10:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_setting",
        sa.Column(
            "company_recency_days",
            sa.Integer(),
            server_default=sa.text("30"),
            nullable=False,
            comment=(
                "Offers first seen earlier than this many days ago are left out of the company "
                "views (ADR-053)."
            ),
        ),
    )
    op.create_check_constraint(
        "company_recency_days_in_range",
        "schedule_setting",
        "company_recency_days BETWEEN 1 AND 365",
    )
    op.create_table_comment(
        "schedule_setting",
        "Daily collection time, time zone and company view limits, one row per owner.",
        existing_comment="Daily collection time and time zone, one row per owner.",
    )


def downgrade() -> None:
    op.create_table_comment(
        "schedule_setting",
        "Daily collection time and time zone, one row per owner.",
        existing_comment=(
            "Daily collection time, time zone and company view limits, one row per owner."
        ),
    )
    op.drop_constraint(
        op.f("ck_schedule_setting_company_recency_days_in_range"),
        "schedule_setting",
        type_="check",
    )
    op.drop_column("schedule_setting", "company_recency_days")
