"""domain packs: which pack lists each term, and which packs the owner switched on (ADR-080)

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-20 15:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

_SOFTWARE_PACK = "software_data_it"


def upgrade() -> None:
    op.create_table(
        "taxonomy_term_pack",
        sa.Column(
            "taxonomy_term_pack_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
            comment="Surrogate primary key of the membership.",
        ),
        sa.Column(
            "taxonomy_term_id", sa.BigInteger(), nullable=False, comment="Term that the pack lists."
        ),
        sa.Column(
            "pack_key",
            sa.String(length=60),
            nullable=False,
            comment="Key of the pack file that lists the term (for example software_data_it).",
        ),
        sa.Column(
            "pack_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
            comment="Version of the pack file in which the term was first listed.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="UTC timestamp at which the row was created.",
        ),
        sa.ForeignKeyConstraint(
            ["taxonomy_term_id"],
            ["taxonomy_term.taxonomy_term_id"],
            name=op.f("fk_taxonomy_term_pack_taxonomy_term_id_taxonomy_term"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("taxonomy_term_pack_id", name=op.f("pk_taxonomy_term_pack")),
        sa.UniqueConstraint(
            "taxonomy_term_id", "pack_key", name=op.f("uq_taxonomy_term_pack_term_pack")
        ),
        comment="Domain packs that list a taxonomy term; a term in no pack is always offered.",
    )
    op.create_table(
        "owner_pack",
        sa.Column(
            "owner_pack_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
            comment="Surrogate primary key of the activation.",
        ),
        sa.Column(
            "owner_id", sa.BigInteger(), nullable=False, comment="Owner who switched the pack on."
        ),
        sa.Column(
            "pack_key",
            sa.String(length=60),
            nullable=False,
            comment="Key of the pack that is switched on.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="UTC timestamp at which the row was created.",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["owner.owner_id"],
            name=op.f("fk_owner_pack_owner_id_owner"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("owner_pack_id", name=op.f("pk_owner_pack")),
        sa.UniqueConstraint("owner_id", "pack_key", name=op.f("uq_owner_pack_owner_id_pack_key")),
        comment="Domain packs each owner has switched on (ADR-080).",
    )
    op.create_index(
        op.f("ix_taxonomy_term_pack_taxonomy_term_id"), "taxonomy_term_pack", ["taxonomy_term_id"]
    )
    op.create_index(op.f("ix_owner_pack_owner_id"), "owner_pack", ["owner_id"])
    # Every role family and sector that exists today is software and IT vocabulary, so it becomes a
    # member of that pack. `other` stays in no pack and is always offered, like the global kinds.
    op.execute(
        f"""
        INSERT INTO taxonomy_term_pack (taxonomy_term_id, pack_key, pack_version)
        SELECT taxonomy_term_id, '{_SOFTWARE_PACK}', 1
        FROM taxonomy_term
        WHERE kind IN ('role_family', 'sector') AND term_key <> 'other'
        """  # noqa: S608
    )
    # An installation that already has a profile keeps seeing exactly the vocabulary it has. A fresh
    # one chooses its packs itself.
    op.execute(
        f"""
        INSERT INTO owner_pack (owner_id, pack_key)
        SELECT DISTINCT owner_id, '{_SOFTWARE_PACK}' FROM career_profile
        """  # noqa: S608
    )


def downgrade() -> None:
    op.drop_table("owner_pack")
    op.drop_table("taxonomy_term_pack")
