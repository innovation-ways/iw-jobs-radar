"""Controlled vocabularies (document 13, section 2) and their versions (ADR-022)."""

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped

from jobs_radar.db.base import Base, CreatedAtMixin
from jobs_radar.db.columns import enum_check, fk_column, pk_column, text_column
from jobs_radar.domain.enums import TaxonomyKind, TermOrigin


class TaxonomyVersion(CreatedAtMixin, Base):
    """One row per taxonomy change; the highest id is the current taxonomy version.

    Extractions and trend aggregates record the version they used so that history stays
    interpretable when terms are added, merged or renamed.
    """

    __tablename__ = "taxonomy_version"
    __table_args__ = {
        "comment": "History of taxonomy changes; the latest row is the current version."
    }

    taxonomy_version_id: Mapped[int] = pk_column("Taxonomy version number (monotonic).")
    description: Mapped[str] = text_column(
        "Why the taxonomy changed, for example 'seed' or a term name."
    )


class TaxonomyTerm(CreatedAtMixin, Base):
    """A term of a controlled vocabulary. Terms are never deleted; merges use ``replaced_by``."""

    __tablename__ = "taxonomy_term"
    __table_args__ = (
        UniqueConstraint("kind", "term_key", name="uq_taxonomy_term_kind_term_key"),
        enum_check("kind", TaxonomyKind),
        enum_check("origin", TermOrigin),
        {"comment": "Controlled-vocabulary terms (role families, sectors, seniority, ...)."},
    )

    taxonomy_term_id: Mapped[int] = pk_column("Surrogate primary key of the term.")
    kind: Mapped[str] = text_column("Vocabulary the term belongs to (taxonomy kind).", length=30)
    term_key: Mapped[str] = text_column("Stable lowercase snake_case key of the term.", length=80)
    label: Mapped[str] = text_column("Human-readable label shown in the interface.", length=120)
    origin: Mapped[str] = text_column(
        "Where the term came from: seed, user or accepted AI proposal.", length=30
    )
    replaced_by_taxonomy_term_id: Mapped[int | None] = fk_column(
        "taxonomy_term.taxonomy_term_id",
        "Term that replaces this one after a merge or rename; null while the term is current.",
        nullable=True,
    )
    introduced_in_taxonomy_version_id: Mapped[int] = fk_column(
        "taxonomy_version.taxonomy_version_id", "Taxonomy version in which the term was introduced."
    )
