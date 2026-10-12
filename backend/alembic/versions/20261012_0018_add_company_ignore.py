"""add the company ignore table (ADR-061)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-12 09:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_ignore",
        sa.Column(
            "company_ignore_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
            comment="Surrogate primary key of the ignore.",
        ),
        sa.Column("owner_id", sa.BigInteger(), nullable=False, comment="Owner who ignores."),
        sa.Column(
            "company_id", sa.BigInteger(), nullable=False, comment="Company that is ignored."
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
        sa.PrimaryKeyConstraint("company_ignore_id"),
        sa.UniqueConstraint("owner_id", "company_id", name="uq_company_ignore_owner_id_company_id"),
        comment="Companies an owner ignores; undoing deletes the row.",
    )
    op.create_index(op.f("ix_company_ignore_company_id"), "company_ignore", ["company_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_company_ignore_company_id"), table_name="company_ignore")
    op.drop_table("company_ignore")
