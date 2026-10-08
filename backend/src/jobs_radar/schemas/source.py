"""API contracts for sources and collection runs (document 07). No credential is ever returned."""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from jobs_radar.domain.enums import RunStatus, RunTrigger, SourceOutcome, SourceType
from jobs_radar.schemas.common import StrictModel

BoardIdentifier = Annotated[str, Field(min_length=1, max_length=100)]


class SourceCreate(StrictModel):
    """Request to add a board; it is validated against the real source before being saved."""

    source_type: SourceType
    external_identifier: BoardIdentifier
    enabled: bool = True


class SourceUpdate(StrictModel):
    """Change a source's settings; ``expected_version`` is the version the client last saw."""

    expected_version: Annotated[int, Field(ge=1)]
    enabled: bool | None = None
    rate_limit_per_minute: Annotated[int, Field(ge=1, le=60)] | None = None


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


class SourceList(StrictModel):
    """All configured sources."""

    items: list[SourceRead]


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
