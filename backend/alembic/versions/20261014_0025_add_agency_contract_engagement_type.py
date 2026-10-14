"""add the agency contract engagement type (ADR-073)

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-14 20:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

from jobs_radar.domain.taxonomy_v3 import TAXONOMY_V3_ADDITIONS, V3_DESCRIPTION, V3_LABELS

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


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
    # The id is explicit (and the sequence moved past it) so that the version is always 3.
    op.bulk_insert(version, [{"taxonomy_version_id": 3, "description": V3_DESCRIPTION}])
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
                "label": V3_LABELS[key],
                "origin": "seed",
                "introduced_in_taxonomy_version_id": 3,
            }
            for kind, keys in TAXONOMY_V3_ADDITIONS.items()
            for key in keys
        ],
    )


def downgrade() -> None:
    # Extractions made with version 3 point at it, so the version and terms stay in that case.
    op.execute(
        "DELETE FROM taxonomy_term WHERE introduced_in_taxonomy_version_id = 3 "
        "AND NOT EXISTS (SELECT 1 FROM job_extraction WHERE taxonomy_version_id = 3)"
    )
    op.execute(
        "DELETE FROM taxonomy_version WHERE taxonomy_version_id = 3 "
        "AND NOT EXISTS (SELECT 1 FROM job_extraction WHERE taxonomy_version_id = 3) "
        "AND NOT EXISTS (SELECT 1 FROM trend_weekly WHERE taxonomy_version_id = 3)"
    )
