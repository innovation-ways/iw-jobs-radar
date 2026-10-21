"""let the owner allow a local model server in the app, not only in the environment (ADR-081)

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-21 10:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every existing owner keeps today's behaviour: only the environment flag allows it.
    op.add_column(
        "privacy_setting",
        sa.Column(
            "allow_local_providers",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment=(
                "Whether the owner lets the app call the local model server the deployment is "
                "configured for (ADR-081); the environment flag can also allow it."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("privacy_setting", "allow_local_providers")
