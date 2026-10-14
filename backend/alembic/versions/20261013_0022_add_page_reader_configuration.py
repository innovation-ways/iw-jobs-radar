"""add the approved reader configurations of careers-page sources (ADR-070)

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-13 19:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from jobs_radar.db.triggers import create_append_only_trigger, drop_append_only_trigger

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "page_reader_configuration",
        sa.Column(
            "page_reader_configuration_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
            comment="Surrogate primary key of the configuration.",
        ),
        sa.Column(
            "source_configuration_id",
            sa.BigInteger(),
            nullable=False,
            comment="Careers-page source the reader belongs to.",
        ),
        sa.Column(
            "revision",
            sa.Integer(),
            nullable=False,
            comment="1 for the first approved reader, then 2, 3, ...",
        ),
        sa.Column(
            "config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Selectors and paging rules (PageReaderConfig, with schema_version).",
        ),
        sa.Column(
            "proposed_by",
            sa.String(length=120),
            nullable=False,
            comment="Who wrote it: model:<provider>:<model>, or owner.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="UTC timestamp at which the row was created.",
        ),
        sa.ForeignKeyConstraint(
            ["source_configuration_id"],
            ["source_configuration.source_configuration_id"],
            name=op.f("fk_page_reader_configuration_source_configuration_id_source_configuration"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "page_reader_configuration_id", name=op.f("pk_page_reader_configuration")
        ),
        sa.UniqueConstraint(
            "source_configuration_id",
            "revision",
            name="uq_page_reader_configuration_source_revision",
        ),
        comment="Approved reader configurations of careers-page sources (append-only).",
    )
    op.create_index(
        op.f("ix_page_reader_configuration_source_configuration_id"),
        "page_reader_configuration",
        ["source_configuration_id"],
    )
    op.execute(create_append_only_trigger("page_reader_configuration"))


def downgrade() -> None:
    op.execute(drop_append_only_trigger("page_reader_configuration"))
    op.drop_index(
        op.f("ix_page_reader_configuration_source_configuration_id"),
        table_name="page_reader_configuration",
    )
    op.drop_table("page_reader_configuration")
