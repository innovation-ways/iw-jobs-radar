"""add the Working Nomads and Remote OK job board source types (ADR-074)

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-14 21:00:00.000000
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_source_configuration_source_type_valid"
_OLD = (
    "source_type IN ('greenhouse', 'lever', 'ashby', 'smartrecruiters', 'eightfold', "
    "'arbeitnow', 'jobicy', 'himalayas', 'itjobs_pt', 'page_jsonld', 'page_config', "
    "'weworkremotely')"
)
_NEW = (
    "source_type IN ('greenhouse', 'lever', 'ashby', 'smartrecruiters', 'eightfold', "
    "'arbeitnow', 'jobicy', 'himalayas', 'itjobs_pt', 'page_jsonld', 'page_config', "
    "'weworkremotely', 'workingnomads', 'remoteok')"
)


def _alter(condition: str) -> None:
    # op.f() keeps the exact name; the naming convention would otherwise prefix it a second time.
    op.drop_constraint(op.f(_CONSTRAINT), "source_configuration", type_="check")
    op.create_check_constraint(op.f(_CONSTRAINT), "source_configuration", condition)


def upgrade() -> None:
    _alter(_NEW)


def downgrade() -> None:
    # The boards cannot exist under the old constraint, so their sources are removed first.
    op.execute(
        "DELETE FROM source_configuration WHERE source_type IN ('workingnomads', 'remoteok')"
    )
    _alter(_OLD)
