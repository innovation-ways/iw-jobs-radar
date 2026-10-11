"""add the non-technical role families and the low-fit floor (ADR-060)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-11 18:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

from jobs_radar.domain.taxonomy_additions import (
    TAXONOMY_V2_ADDITIONS,
    V2_DESCRIPTION,
    V2_LABELS,
)

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_OLD_COMMENT = "Daily collection time, time zone and company view limits, one row per owner."
_NEW_COMMENT = (
    "Daily collection time, time zone and inbox and company view limits, one row per owner."
)


def upgrade() -> None:
    version = sa.table(
        "taxonomy_version",
        sa.column("taxonomy_version_id", sa.BigInteger),
        sa.column("description", sa.String),
    )
    term = sa.table(
        "taxonomy_term",
        sa.column("kind", sa.String),
        sa.column("term_key", sa.String),
        sa.column("label", sa.String),
        sa.column("origin", sa.String),
        sa.column("introduced_in_taxonomy_version_id", sa.BigInteger),
    )
    # The id is explicit (and the sequence moved past it) so that the version is always 2.
    op.bulk_insert(version, [{"taxonomy_version_id": 2, "description": V2_DESCRIPTION}])
    op.execute(
        "SELECT setval(pg_get_serial_sequence('taxonomy_version', 'taxonomy_version_id'), "
        "(SELECT max(taxonomy_version_id) FROM taxonomy_version))"
    )
    op.bulk_insert(
        term,
        [
            {
                "kind": kind,
                "term_key": key,
                "label": V2_LABELS[key],
                "origin": "seed",
                "introduced_in_taxonomy_version_id": 2,
            }
            for kind, keys in TAXONOMY_V2_ADDITIONS.items()
            for key in keys
        ],
    )

    op.add_column(
        "schedule_setting",
        sa.Column(
            "set_aside_below_fit",
            sa.Integer(),
            server_default=sa.text("20"),
            nullable=False,
            comment=(
                "Recommended jobs with a fit below this value are listed as set aside in the "
                "inbox; 0 turns the rule off (ADR-060)."
            ),
        ),
    )
    op.create_check_constraint(
        "set_aside_below_fit_in_range",
        "schedule_setting",
        "set_aside_below_fit BETWEEN 0 AND 100",
    )
    op.create_table_comment("schedule_setting", _NEW_COMMENT, existing_comment=_OLD_COMMENT)


def downgrade() -> None:
    op.create_table_comment("schedule_setting", _OLD_COMMENT, existing_comment=_NEW_COMMENT)
    op.drop_constraint(
        op.f("ck_schedule_setting_set_aside_below_fit_in_range"),
        "schedule_setting",
        type_="check",
    )
    op.drop_column("schedule_setting", "set_aside_below_fit")
    # Extractions made with version 2 point at it, so the version and terms stay in that case.
    op.execute(
        "DELETE FROM taxonomy_term WHERE introduced_in_taxonomy_version_id = 2 "
        "AND NOT EXISTS (SELECT 1 FROM job_extraction WHERE taxonomy_version_id = 2)"
    )
    op.execute(
        "DELETE FROM taxonomy_version WHERE taxonomy_version_id = 2 "
        "AND NOT EXISTS (SELECT 1 FROM job_extraction WHERE taxonomy_version_id = 2) "
        "AND NOT EXISTS (SELECT 1 FROM trend_weekly WHERE taxonomy_version_id = 2)"
    )
