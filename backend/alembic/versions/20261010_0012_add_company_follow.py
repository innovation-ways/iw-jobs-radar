"""add the company follow table (ADR-053)

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-10 09:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_follow",
        sa.Column(
            "company_follow_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
            comment="Surrogate primary key of the follow.",
        ),
        sa.Column("owner_id", sa.BigInteger(), nullable=False, comment="Owner who follows."),
        sa.Column(
            "company_id", sa.BigInteger(), nullable=False, comment="Company that is followed."
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="UTC timestamp at which the row was created.",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["owner.owner_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["company.company_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("company_follow_id"),
        sa.UniqueConstraint("owner_id", "company_id", name="uq_company_follow_owner_id_company_id"),
        comment="Companies an owner follows; unfollowing deletes the row.",
    )
    op.create_index(op.f("ix_company_follow_company_id"), "company_follow", ["company_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_company_follow_company_id"), table_name="company_follow")
    op.drop_table("company_follow")
