"""API contracts for the daily digest (document 07, section 5)."""

from datetime import datetime
from typing import Literal

from jobs_radar.schemas.common import StrictModel
from jobs_radar.schemas.inbox import InboxItemSummary
from jobs_radar.schemas.source import CollectionRunRead


class ChangedItemRead(StrictModel):
    """A shortlisted job whose posting changed materially."""

    item: InboxItemSummary
    changed_fields: list[str]
    changed_at: datetime


class SourceHealthRead(StrictModel):
    """An enabled source that needs attention."""

    source_configuration_id: int
    display_name: str
    status: Literal["failed", "stale", "never_run"]
    error_class: str | None
    error_message: str | None
    last_run_at: datetime | None


class DigestCounts(StrictModel):
    """Entries per section."""

    new_high_fit: int
    changed_shortlisted: int
    sources_needing_attention: int


class DigestRead(StrictModel):
    """The daily digest: what is worth looking at today."""

    generated_at: datetime
    since: datetime
    search_intent_id: int | None
    alert_threshold: int
    new_high_fit: list[InboxItemSummary]
    changed_shortlisted: list[ChangedItemRead]
    source_health: list[SourceHealthRead]
    last_run: CollectionRunRead | None
    counts: DigestCounts
