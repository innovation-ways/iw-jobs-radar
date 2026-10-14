"""add the freelancermap job board source type (ADR-075)

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-14 22:00:00.000000
"""

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_source_configuration_source_type_valid"
_OLD = (
    "source_type IN ('greenhouse', 'lever', 'ashby', 'smartrecruiters', 'eightfold', "
    "'arbeitnow', 'jobicy', 'himalayas', 'itjobs_pt', 'page_jsonld', 'page_config', "
    "'weworkremotely', 'workingnomads', 'remoteok')"
)
_NEW = (
    "source_type IN ('greenhouse', 'lever', 'ashby', 'smartrecruiters', 'eightfold', "
    "'arbeitnow', 'jobicy', 'himalayas', 'itjobs_pt', 'page_jsonld', 'page_config', "
    "'weworkremotely', 'workingnomads', 'remoteok', 'freelancermap')"
)


def _alter(condition: str) -> None:
    # op.f() keeps the exact name; the naming convention would otherwise prefix it a second time.
    op.drop_constraint(op.f(_CONSTRAINT), "source_configuration", type_="check")
    op.create_check_constraint(op.f(_CONSTRAINT), "source_configuration", condition)


def upgrade() -> None:
    _alter(_NEW)


def downgrade() -> None:
    # The board cannot exist under the old constraint, so its sources are removed first.
    op.execute("DELETE FROM source_configuration WHERE source_type = 'freelancermap'")
    _alter(_OLD)
