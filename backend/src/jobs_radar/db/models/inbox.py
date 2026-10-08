"""The owner's personal triage state, separate from job facts (ADR-006, LLD section 3)."""

from datetime import datetime
from typing import Any

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped

from jobs_radar.db.base import Base, CreatedAtMixin, TimestampMixin
from jobs_radar.db.columns import (
    bool_column,
    enum_check,
    fk_column,
    json_column,
    pk_column,
    text_column,
    timestamp_column,
    version_column,
)
from jobs_radar.domain.enums import Actor, InboxAction, InboxState


class JobInboxItem(TimestampMixin, Base):
    """One owner's inbox entry for one opportunity."""

    __tablename__ = "job_inbox_item"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "job_opportunity_id", name="uq_job_inbox_item_owner_id_job_opportunity_id"
        ),
        enum_check("state", InboxState),
        {"comment": "Per-owner triage state of an opportunity."},
    )

    job_inbox_item_id: Mapped[int] = pk_column("Surrogate primary key of the inbox item.")
    owner_id: Mapped[int] = fk_column("owner.owner_id", "Owner of the item.", index=False)
    job_opportunity_id: Mapped[int] = fk_column(
        "job_opportunity.job_opportunity_id", "Opportunity the item tracks."
    )
    state: Mapped[str] = text_column(
        "unread, read, updated_unread, ignored, archived or applied.",
        length=20,
        default="unread",
        index=True,
    )
    is_shortlisted: Mapped[bool] = bool_column(
        "Shortlist flag, independent of the state.", default=False
    )
    read_at: Mapped[datetime | None] = timestamp_column(
        "UTC time at which the owner first opened it.", nullable=True
    )
    ignore_reason: Mapped[str | None] = text_column(
        "Reason recorded when ignoring.", length=100, nullable=True
    )
    note: Mapped[str | None] = text_column("Private note of the owner.", nullable=True)
    applied_at: Mapped[datetime | None] = timestamp_column(
        "Date of the application the owner recorded.", nullable=True
    )
    application_url: Mapped[str | None] = text_column(
        "Link recorded with the application.", nullable=True
    )
    version: Mapped[int] = version_column()


class InboxEvent(CreatedAtMixin, Base):
    """Audit stream of everything that happened to an inbox item (append-only)."""

    __tablename__ = "inbox_event"
    __table_args__ = (
        enum_check("action", InboxAction),
        enum_check("actor", Actor),
        {"comment": "Append-only audit stream of inbox actions."},
    )

    inbox_event_id: Mapped[int] = pk_column("Surrogate primary key of the event.")
    job_inbox_item_id: Mapped[int] = fk_column(
        "job_inbox_item.job_inbox_item_id", "Item the event belongs to.", ondelete="CASCADE"
    )
    action: Mapped[str] = text_column("Action performed.", length=30)
    actor: Mapped[str] = text_column("user or system.", length=10)
    from_state: Mapped[str | None] = text_column(
        "State before the action.", length=20, nullable=True
    )
    to_state: Mapped[str] = text_column("State after the action.", length=20)
    metadata_json: Mapped[Any] = json_column(
        "Safe action metadata (reason, dates); no personal content."
    )
