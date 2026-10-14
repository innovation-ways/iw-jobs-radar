"""add the careers-page source types (ADR-070)

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-13 18:00:00.000000
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_source_configuration_source_type_valid"
_OLD = (
    "source_type IN ('greenhouse', 'lever', 'ashby', 'smartrecruiters', 'eightfold', "
    "'arbeitnow', 'jobicy', 'himalayas', 'itjobs_pt')"
)
_NEW = (
    "source_type IN ('greenhouse', 'lever', 'ashby', 'smartrecruiters', 'eightfold', "
    "'arbeitnow', 'jobicy', 'himalayas', 'itjobs_pt', 'page_jsonld', 'page_config')"
)


def _alter(condition: str) -> None:
    # op.f() keeps the exact name; the naming convention would otherwise prefix it a second time.
    op.drop_constraint(op.f(_CONSTRAINT), "source_configuration", type_="check")
    op.create_check_constraint(op.f(_CONSTRAINT), "source_configuration", condition)


def upgrade() -> None:
    _alter(_NEW)


def downgrade() -> None:
    # Page sources cannot exist under the old constraint, so they are removed first.
    op.execute(
        "DELETE FROM source_configuration WHERE source_type IN ('page_jsonld', 'page_config')"
    )
    _alter(_OLD)
