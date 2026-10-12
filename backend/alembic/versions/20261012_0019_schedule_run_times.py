"""the schedule keeps a list of daily run times (ADR-062)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-12 10:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_OLD_COMMENT = (
    "Daily collection time, time zone and inbox and company view limits, one row per owner."
)
_NEW_COMMENT = (
    "Daily collection times, time zone and inbox and company view limits, one row per owner."
)


def upgrade() -> None:
    op.add_column(
        "schedule_setting",
        sa.Column(
            "run_times_local",
            postgresql.ARRAY(sa.Time()),
            nullable=True,
            comment="Local wall-clock times of the daily runs, sorted, one to twelve (ADR-062).",
        ),
    )
    # The single time becomes a one-item list, so the schedule keeps running as before.
    op.execute("UPDATE schedule_setting SET run_times_local = ARRAY[run_time_local]")
    op.alter_column("schedule_setting", "run_times_local", nullable=False)
    op.drop_column("schedule_setting", "run_time_local")
    op.create_check_constraint(
        "run_times_local_in_range",
        "schedule_setting",
        "cardinality(run_times_local) BETWEEN 1 AND 12",
    )
    op.create_table_comment("schedule_setting", _NEW_COMMENT, existing_comment=_OLD_COMMENT)


def downgrade() -> None:
    op.add_column(
        "schedule_setting",
        sa.Column(
            "run_time_local",
            sa.Time(),
            nullable=True,
            comment="Local wall-clock time of the daily run.",
        ),
    )
    # Only the first (earliest) time survives the way back.
    op.execute("UPDATE schedule_setting SET run_time_local = run_times_local[1]")
    op.alter_column("schedule_setting", "run_time_local", nullable=False)
    op.drop_constraint("ck_schedule_setting_run_times_local_in_range", "schedule_setting")
    op.drop_column("schedule_setting", "run_times_local")
    op.create_table_comment("schedule_setting", _OLD_COMMENT, existing_comment=_NEW_COMMENT)
