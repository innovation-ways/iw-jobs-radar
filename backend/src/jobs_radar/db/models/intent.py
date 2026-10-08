"""Search intents and their immutable revisions (document 13, section 4)."""

from typing import Any

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped

from jobs_radar.db.base import Base, CreatedAtMixin, TimestampMixin
from jobs_radar.db.columns import (
    bool_column,
    fk_column,
    int_column,
    json_column,
    pk_column,
    text_column,
    version_column,
)


class SearchIntent(TimestampMixin, Base):
    """What the owner is looking for; versioned independently from the profile (ADR-003)."""

    __tablename__ = "search_intent"
    __table_args__ = {"comment": "Search intents linked to a career profile."}

    search_intent_id: Mapped[int] = pk_column("Surrogate primary key of the intent.")
    owner_id: Mapped[int] = fk_column("owner.owner_id", "Owner of the intent.")
    career_profile_id: Mapped[int] = fk_column(
        "career_profile.career_profile_id", "Profile the intent belongs to.", ondelete="CASCADE"
    )
    title: Mapped[str] = text_column("Intent name chosen by the owner.", length=120)
    enabled: Mapped[bool] = bool_column(
        "Whether the intent takes part in collection and digests.", default=True
    )
    current_intent_revision_id: Mapped[int | None] = fk_column(
        "intent_revision.intent_revision_id",
        "Latest revision; null until the first revision is created.",
        nullable=True,
        use_alter=True,
        name="fk_search_intent_current_intent_revision",
    )
    version: Mapped[int] = version_column()


class IntentRevision(CreatedAtMixin, Base):
    """An immutable snapshot of an intent: stances, rules, pay, weights, threshold (append-only)."""

    __tablename__ = "intent_revision"
    __table_args__ = (
        UniqueConstraint(
            "search_intent_id",
            "revision_number",
            name="uq_intent_revision_search_intent_id_revision_number",
        ),
        CheckConstraint("revision_number >= 1", name="revision_number_positive"),
        {"comment": "Immutable search-intent revisions (append-only)."},
    )

    intent_revision_id: Mapped[int] = pk_column("Surrogate primary key of the revision.")
    search_intent_id: Mapped[int] = fk_column(
        "search_intent.search_intent_id", "Intent the revision belongs to.", ondelete="CASCADE"
    )
    revision_number: Mapped[int] = int_column("1-based sequence number within the intent.")
    intent_json: Mapped[Any] = json_column("Intent definition (document 13, section 4).")
    change_summary: Mapped[str | None] = text_column(
        "Short description of what changed.", nullable=True
    )
