"""let the owner switch a taxonomy term off and record when it changed (ADR-080, phase 3)

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-20 13:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every existing term stays active, so nothing changes for the current vocabulary.
    op.add_column(
        "taxonomy_term",
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
            comment=(
                "Whether the term is offered for new choices and to the extraction model; "
                "false keeps it in stored intents and history."
            ),
        ),
    )
    op.add_column(
        "taxonomy_term",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="UTC timestamp of the last modification of the row.",
        ),
    )


def downgrade() -> None:
    op.drop_column("taxonomy_term", "updated_at")
    op.drop_column("taxonomy_term", "is_active")
