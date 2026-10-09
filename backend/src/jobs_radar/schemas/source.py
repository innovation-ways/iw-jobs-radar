"""API contracts for sources and collection runs (document 07). No credential is ever returned."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field

from jobs_radar.domain.enums import (
    RunStatus,
    RunTrigger,
    SourceCategory,
    SourceOutcome,
    SourceType,
)
from jobs_radar.schemas.common import StrictModel
from jobs_radar.schemas.source_filters import JobBoardFilters

BoardIdentifier = Annotated[str, Field(min_length=1, max_length=100)]


class SourceCreate(StrictModel):
    """Request to add a source; it is validated against the real source before being saved.

    A company board is added by its token. A job board is added from the catalogue: its
    ``source_type`` and ``external_identifier`` are the catalogue key, a board that needs a key
    takes it in ``credential`` (write-only), and ``filters`` narrow what is kept.
    """

    source_type: SourceType
    external_identifier: BoardIdentifier
    enabled: bool = True
    credential: str | None = Field(default=None, min_length=1, max_length=500, repr=False)
    filters: JobBoardFilters | None = None
    # Company boards whose ATS publishes no company name (Lever, Ashby) take the owner's wording.
    display_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class SourcePreviewRequest(StrictModel):
    """Ask how many postings of a catalogue board would be kept, without saving anything."""

    catalogue_key: BoardIdentifier
    credential: str | None = Field(default=None, min_length=1, max_length=500, repr=False)
    filters: JobBoardFilters | None = None


class SourcePreviewRead(StrictModel):
    """What a preview found; the match count is a lower bound when the scan stopped early."""

    display_name: str
    postings_total: int
    postings_matching: int
    matching_is_lower_bound: bool


class SourceUpdate(StrictModel):
    """Change a source's settings; ``expected_version`` is the version the client last saw."""

    expected_version: Annotated[int, Field(ge=1)]
    enabled: bool | None = None
    rate_limit_per_minute: Annotated[int, Field(ge=1, le=60)] | None = None
    filters: JobBoardFilters | None = None


class SourceResultRead(StrictModel):
    """What happened to one source in one run."""

    collection_run_id: int
    source_configuration_id: int
    outcome: SourceOutcome
    started_at: datetime
    finished_at: datetime
    collected_count: int
    new_count: int
    updated_count: int
    deduplicated_count: int
    closed_count: int
    dropped_count: int
    http_status: int | None
    error_class: str | None
    error_message: str | None
    duration_ms: int


class SourceRead(StrictModel):
    """A configured source with its latest status."""

    source_configuration_id: int
    source_type: SourceType
    external_identifier: str
    display_name: str
    company_id: int | None
    company_name: str | None
    url: str
    enabled: bool
    rate_limit_per_minute: int
    version: int
    open_postings: int
    last_result: SourceResultRead | None
    # Job boards (ADR-049): company boards leave the catalogue-derived fields empty.
    category: SourceCategory
    coverage_note: str | None
    filters: JobBoardFilters | None
    credential_status: Literal["saved", "none", "not_needed"]
    credential_updated_at: datetime | None
    terms_url: str | None
    attribution_text: str | None
    next_run_allowed_at: datetime | None


class SourceList(StrictModel):
    """All configured sources."""

    items: list[SourceRead]


class CatalogueEntryRead(StrictModel):
    """A job board the owner can add; the endpoint stays inside the server."""

    catalogue_key: str
    display_name: str
    coverage_note: str
    homepage_url: str
    requires_credential: bool
    credential_label: str | None
    terms_note: str
    terms_url: str
    terms_read_on: date
    attribution_text: str
    delay_note: str | None
    min_interval_minutes: int
    default_filters: JobBoardFilters
    available_categories: list[str]
    already_added: bool


class CatalogueList(StrictModel):
    """The job boards that can be added now."""

    items: list[CatalogueEntryRead]


class OnsiteAreaRead(StrictModel):
    """A place and radius where hybrid or on-site work is acceptable."""

    place: str
    radius_km: int


class SourceScopeRead(StrictModel):
    """Where the owner can work, as derived from the profile and the enabled intents (read-only)."""

    configured: bool
    country_codes: list[str]
    include_worldwide: bool
    any_country: bool
    onsite_areas: list[OnsiteAreaRead]


class CollectionRunRead(StrictModel):
    """A collection run and the per-source results recorded so far."""

    collection_run_id: int
    source_configuration_id: int | None
    trigger: RunTrigger
    status: RunStatus
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_class: str | None
    results: list[SourceResultRead]


class CollectionRunPage(StrictModel):
    """One page of run history, newest first; pass the cursor back to get older runs."""

    items: list[CollectionRunRead]
    next_before_collection_run_id: int | None
