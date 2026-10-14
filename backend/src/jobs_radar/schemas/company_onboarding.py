"""API contracts for following a company from its website and careers addresses (ADR-070)."""

from typing import Annotated, Literal

from pydantic import Field

from jobs_radar.domain.enums import SourceType
from jobs_radar.schemas.common import StrictModel
from jobs_radar.schemas.page_reader import PageReaderConfig

CompanyName = Annotated[str, Field(min_length=1, max_length=200)]
Address = Annotated[str, Field(min_length=1, max_length=500)]
Layer = Literal["ats", "structured_page"]
Outcome = Literal[
    "detected",
    "ambiguous",
    "unsupported",
    "script_only",
    "blocked",
    "unreachable",
    "already_followed",
]


class OnboardingDetectRequest(StrictModel):
    """The three things the owner knows about a company; nothing is saved by a detection."""

    name: CompanyName
    website_url: Address
    careers_url: Address


class DetectedBoardRead(StrictModel):
    """A board the careers page can be collected from, already checked against the real board."""

    source_type: SourceType
    identifier: str
    display_name: str
    postings_count: int
    layer: Layer


class OnboardingDetectionRead(StrictModel):
    """What the careers address leads to, with the addresses in the form they would be saved."""

    outcome: Outcome
    website_url: str
    careers_url: str
    candidates: list[DetectedBoardRead]
    reason: str | None
    existing_company_id: int | None


class SourceChoice(StrictModel):
    """The board the owner chose among the detected ones."""

    source_type: SourceType
    identifier: Annotated[str, Field(min_length=1, max_length=200)]


class OnboardingConfirm(StrictModel):
    """Create the company, follow it and, when a board is chosen, add and collect it.

    Without ``source`` the company is followed with its website and careers address and no
    automatic collection (ADR-070.4). ``filters_enabled`` turns on the opt-in area and location
    filters of ADR-051 for the new source.
    """

    name: CompanyName
    website_url: Address
    careers_url: Address
    source: SourceChoice | None = None
    # The owner-approved reader of a careers page that has no known board (ADR-070 layer 3); it
    # replaces ``source``, and ``reader_proposed_by`` is the provenance the proposal came with.
    reader: PageReaderConfig | None = None
    reader_proposed_by: Annotated[str, Field(max_length=120)] | None = None
    filters_enabled: bool = True


class OnboardingResultRead(StrictModel):
    """What confirming created."""

    company_id: int
    company_name: str
    is_followed: bool
    source_configuration_id: int | None
    collection_run_id: int | None
    collecting: bool


class ReaderPostingRead(StrictModel):
    """A posting a proposed reader finds on the careers page."""

    title: str
    url: str
    location: str


class ReaderProposalRead(StrictModel):
    """A reader proposed by the local model, with what it finds, for the owner to review."""

    reader: PageReaderConfig
    preview: list[ReaderPostingRead]
    proposed_by: str


class ReaderReplace(StrictModel):
    """Approve a new reader for an existing careers-page source (the old one stays in history)."""

    expected_version: Annotated[int, Field(ge=1)]
    reader: PageReaderConfig
    proposed_by: Annotated[str, Field(max_length=120)] = "owner"
