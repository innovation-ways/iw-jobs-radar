"""add the schedule and travel vocabularies to the taxonomy (ADR-080, phase 6b)

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-20 19:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

from jobs_radar.domain.taxonomy_v4 import TAXONOMY_V4_ADDITIONS, V4_DESCRIPTION, V4_LABELS

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_taxonomy_term_kind_valid"
_OLD_KINDS = (
    "role_family",
    "sector",
    "seniority_level",
    "engagement_type",
    "work_arrangement",
    "employer_type",
    "benefit",
)
_NEW_KINDS = (*_OLD_KINDS, "schedule", "travel_level")


def _condition(kinds: tuple[str, ...]) -> str:
    return "kind IN (" + ", ".join(f"'{kind}'" for kind in kinds) + ")"


def _alter(kinds: tuple[str, ...]) -> None:
    # op.f() keeps the exact name; the naming convention would otherwise prefix it a second time.
    op.drop_constraint(op.f(_CONSTRAINT), "taxonomy_term", type_="check")
    op.create_check_constraint(op.f(_CONSTRAINT), "taxonomy_term", _condition(kinds))


def upgrade() -> None:
    _alter(_NEW_KINDS)
    # The version id comes from the sequence, not a fixed number: an installation that has already
    # loaded domain packs has recorded versions past 3.
    version_id = (
        op.get_bind()
        .execute(
            sa.text(
                "INSERT INTO taxonomy_version (description) VALUES (:description) "
                "RETURNING taxonomy_version_id"
            ),
            {"description": V4_DESCRIPTION},
        )
        .scalar_one()
    )
    term = sa.table(
        "taxonomy_term",
        sa.column("kind", sa.String),
        sa.column("term_key", sa.String),
        sa.column("label", sa.String),
        sa.column("origin", sa.String),
        sa.column("introduced_in_taxonomy_version_id", sa.BigInteger),
    )
    op.bulk_insert(
        term,
        [
            {
                "kind": kind,
                "term_key": key,
                "label": V4_LABELS[key],
                "origin": "seed",
                "introduced_in_taxonomy_version_id": version_id,
            }
            for kind, keys in TAXONOMY_V4_ADDITIONS.items()
            for key in keys
        ],
    )


def downgrade() -> None:
    # The new vocabularies cannot exist under the old constraint, so their terms go. Saved intents
    # that listed them keep working on the code of the old version, which does not know the groups.
    op.execute("DELETE FROM taxonomy_term WHERE kind IN ('schedule', 'travel_level')")
    _alter(_OLD_KINDS)
