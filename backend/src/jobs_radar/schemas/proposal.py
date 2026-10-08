"""API contracts for CV proposals and their review (document 07, section 3)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import Field

from jobs_radar.schemas.common import StrictModel
from jobs_radar.schemas.profile_api import ProfileRead


class ConsentGiven(StrictModel):
    """The owner's confirmation that this CV may go to this connection and model."""

    provider_connection_id: int = Field(ge=1)
    model_id: Annotated[str, Field(min_length=1, max_length=120)]


class ProposalRequest(StrictModel):
    """Generate proposals for a profile; ``consent`` is required for a remote provider."""

    career_profile_id: int = Field(ge=1)
    consent: ConsentGiven | None = None


class ProposalItemRead(StrictModel):
    """One proposed fact with its supporting excerpt and review state."""

    proposal_item_id: int
    path: str
    value: Any
    source_excerpt: str | None
    confidence: Decimal | None
    review_status: Literal["pending", "accepted", "edited", "rejected", "deferred"]
    edited_value: Any | None
    reviewed_at: datetime | None


class ProposalRead(StrictModel):
    """A proposal with the provider metadata (never a credential) and its items."""

    profile_proposal_id: int
    career_profile_id: int
    document_id: int | None
    provider_type: str | None
    provider_model: str | None
    prompt_version: str | None
    redaction_policy: str | None
    consent: dict[str, Any] | None
    status: Literal["pending", "completed"]
    completed_at: datetime | None
    created_at: datetime
    items: list[ProposalItemRead]


class DecisionRequest(StrictModel):
    """The decision on one item; ``value`` replaces the proposal for ``edit``."""

    proposal_item_id: int = Field(ge=1)
    decision: Literal["accept", "edit", "reject", "defer"]
    value: Any | None = None


class ReviewRequest(StrictModel):
    """Apply a set of decisions atomically."""

    profile_proposal_id: int = Field(ge=1)
    expected_current_revision: int | None = Field(default=None, ge=1)
    decisions: list[DecisionRequest] = Field(max_length=500)
    change_summary: Annotated[str, Field(max_length=300)] | None = None


class ReviewResponse(StrictModel):
    """The outcome: whether a revision was created, the profile and the proposal."""

    created: bool
    profile: ProfileRead | None
    proposal: ProposalRead
