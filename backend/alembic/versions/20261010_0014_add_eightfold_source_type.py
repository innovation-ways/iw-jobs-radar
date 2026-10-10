"""add the Eightfold source type

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-10 14:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_source_configuration_source_type_valid"
_OLD = (
    "source_type IN ('greenhouse', 'lever', 'ashby', 'smartrecruiters', 'arbeitnow', 'jobicy', "
    "'himalayas', 'itjobs_pt')"
)
_NEW = (
    "source_type IN ('greenhouse', 'lever', 'ashby', 'smartrecruiters', 'eightfold', "
    "'arbeitnow', 'jobicy', 'himalayas', 'itjobs_pt')"
)
_OLD_COMMENT = "Adapter kind: an ATS company board or a job board (ADR-049, ADR-050)."
_NEW_COMMENT = "Adapter kind: an ATS company board or a job board (ADR-049, ADR-050, ADR-055)."


def _alter(condition: str, comment: str, existing_comment: str) -> None:
    # op.f() keeps the exact name; the naming convention would otherwise prefix it a second time.
    op.drop_constraint(op.f(_CONSTRAINT), "source_configuration", type_="check")
    op.create_check_constraint(op.f(_CONSTRAINT), "source_configuration", condition)
    op.alter_column(
        "source_configuration",
        "source_type",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        comment=comment,
        existing_comment=existing_comment,
    )


def upgrade() -> None:
    _alter(_NEW, _NEW_COMMENT, _OLD_COMMENT)


def downgrade() -> None:
    # Eightfold sources cannot exist under the old constraint, so they are removed first.
    op.execute("DELETE FROM source_configuration WHERE source_type = 'eightfold'")
    _alter(_OLD, _OLD_COMMENT, _NEW_COMMENT)
