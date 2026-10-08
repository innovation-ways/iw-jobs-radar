"""API contracts for the inbox (document 07, section 5)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, Field, StringConstraints

from jobs_radar.schemas.common import StrictModel
from jobs_radar.schemas.evaluation import (
    DimensionQuality,
    DimensionRead,
    DimensionStatus,
    FitBand,
    GateRead,
    RecommendationValue,
)

InboxStateName = Literal["unread", "read", "updated_unread", "ignored", "archived", "applied"]
OwnerAction = Literal[
    "open",
    "mark_unread",
    "shortlist",
    "unshortlist",
    "ignore",
    "restore",
    "archive",
    "record_application",
]
InboxSort = Literal["fit_desc", "newest", "oldest"]
Reason = Annotated[str, StringConstraints(max_length=100)]
Note = Annotated[str, StringConstraints(max_length=2000)]


class InboxActionRequest(StrictModel):
    """One owner action; ``expected_version`` is the item version the client last saw."""

    action: OwnerAction
    expected_version: int = Field(ge=1)
    reason: Reason | None = None
    note: Note | None = None
    applied_at: datetime | None = None
    application_url: AnyHttpUrl | None = None


class SignalRead(StrictModel):
    """A dimension's status, shown as a small signal on the card."""

    dimension_key: str
    status: DimensionStatus
    quality: DimensionQuality | None
    excluded: bool


class SourceRef(StrictModel):
    """A listing of the opportunity on one source."""

    job_posting_id: int
    source_type: str
    source_name: str
    url: str
    first_seen_at: datetime
    closed: bool
    job_opportunity_link_id: int
    link_state: Literal["auto", "possible", "confirmed"]
    similarity: float


class EvaluationBrief(StrictModel):
    """The score of the job under the chosen intent."""

    match_evaluation_id: int
    policy_version: str
    fit_score: int
    fit_band: FitBand
    recommendation: RecommendationValue
    gates: list[GateRead]
    profile_revision_id: int
    intent_revision_id: int
    created_at: datetime


class InboxItemSummary(StrictModel):
    """A row of the inbox list."""

    job_inbox_item_id: int
    job_opportunity_id: int
    job_posting_id: int
    state: InboxStateName
    is_shortlisted: bool
    version: int
    title: str
    company_name: str
    locations: list[str]
    first_seen_at: datetime
    last_seen_at: datetime
    closed: bool
    evaluated: bool
    evaluation: EvaluationBrief | None
    signals: list[SignalRead]
    sources: list[SourceRef]
    possible_duplicate: bool
    applied_at: datetime | None
    note: str | None


class InboxCounts(StrictModel):
    """Items per state, for the tabs."""

    unread: int
    read: int
    updated_unread: int
    ignored: int
    archived: int
    applied: int
    shortlisted: int
    total: int


class InboxList(StrictModel):
    """One page of the inbox."""

    items: list[InboxItemSummary]
    next_cursor: str | None
    counts: InboxCounts
    search_intent_id: int | None


class InboxEventRead(StrictModel):
    """One entry of an item's history."""

    inbox_event_id: int
    action: str
    actor: Literal["user", "system"]
    from_state: str | None
    to_state: str
    created_at: datetime


class ChangeRead(StrictModel):
    """The latest material change to the job."""

    changed_fields: list[str]
    created_at: datetime


class InboxItemDetail(InboxItemSummary):
    """An item with the job text, the evidence behind its score and its history."""

    description_text: str
    apply_url: str | None
    read_at: datetime | None
    ignore_reason: str | None
    application_url: str | None
    dimensions: list[DimensionRead]
    events: list[InboxEventRead]
    last_change: ChangeRead | None


class InboxActionResponse(StrictModel):
    """The item after the action and the event it appended (``null`` when nothing changed)."""

    item: InboxItemSummary
    event: InboxEventRead | None


class LinkDecisionResponse(StrictModel):
    """The opportunity the posting belongs to after the owner's decision."""

    job_opportunity_id: int
    state: Literal["confirmed", "rejected"]
