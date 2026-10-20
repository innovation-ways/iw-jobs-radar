"""skills can be tools or equipment and credentials (ADR-080, phase 6a)

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-20 17:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_skill_kind_valid"
_OLD = "kind IN ('technology', 'domain_knowledge', 'method')"
_NEW = "kind IN ('technology', 'domain_knowledge', 'method', 'tool_equipment', 'credential')"
_COMMENT_OLD = "Category: technology, domain knowledge or method."
_COMMENT_NEW = "Category: technology, domain knowledge, method, tool or equipment, or credential."


def _alter(condition: str, comment: str) -> None:
    # op.f() keeps the exact name; the naming convention would otherwise prefix it a second time.
    op.drop_constraint(op.f(_CONSTRAINT), "skill", type_="check")
    op.create_check_constraint(op.f(_CONSTRAINT), "skill", condition)
    op.alter_column(
        "skill",
        "kind",
        existing_type=sa.String(length=30),
        existing_nullable=False,
        comment=comment,
    )


def upgrade() -> None:
    _alter(_NEW, _COMMENT_NEW)


def downgrade() -> None:
    # A skill of a new kind cannot exist under the old constraint; profiles refer to skills by id,
    # so such skills are turned into method skills (the closest old kind) instead of deleted.
    op.execute("UPDATE skill SET kind = 'method' WHERE kind IN ('tool_equipment', 'credential')")
    _alter(_OLD, _COMMENT_OLD)
