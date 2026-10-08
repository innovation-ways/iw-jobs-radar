"""Audit trail for export and deletion, free of deleted content (TR-8.4)."""

from typing import Any

from sqlalchemy.orm import Mapped

from jobs_radar.db.base import Base, CreatedAtMixin
from jobs_radar.db.columns import fk_column, json_column, pk_column, text_column


class AuditEvent(CreatedAtMixin, Base):
    """A record that an auditable operation happened; it never contains deleted content."""

    __tablename__ = "audit_event"
    __table_args__ = {"comment": "Append-only audit trail of export and deletion operations."}

    audit_event_id: Mapped[int] = pk_column("Surrogate primary key of the audit event.")
    owner_id: Mapped[int | None] = fk_column(
        "owner.owner_id", "Owner the operation concerned, if any.", nullable=True
    )
    action: Mapped[str] = text_column(
        "Operation, for example profile_deleted or profile_exported.", length=60
    )
    subject_type: Mapped[str] = text_column("Kind of subject the operation touched.", length=60)
    metadata_json: Mapped[Any] = json_column("Counts and identifiers only; never content.")
