"""API contracts for the company dossier (document 07, document 13 section 9)."""

from datetime import date, datetime
from typing import Any, Literal

from jobs_radar.domain.enums import SourceOutcome, SourceType
from jobs_radar.schemas.common import StrictModel
from jobs_radar.schemas.evaluation import FitBand


class FactRead(StrictModel):
    """A current fact with its provenance; ``label`` tells how much to trust it."""

    fact_key: str
    value: Any
    origin: Literal["source", "public_dataset", "ai_inference", "user"]
    label: Literal["Source", "AI inference", "You"]
    source_name: str
    source_url: str | None
    retrieved_at: datetime
    licence: str | None
    confidence: float | None


class CandidateRead(StrictModel):
    """An entity that may be the company, waiting for the owner's decision."""

    company_enrichment_candidate_id: int
    source_name: str
    external_id: str
    label: str
    description: str | None
    website: str | None


class OfferRead(StrictModel):
    """One opportunity of the company."""

    job_opportunity_id: int
    title: str
    source_url: str
    first_seen_at: datetime
    closed: bool
    fit_score: int | None
    recommendation: str | None
    fit_band: FitBand | None
    state: str | None
    is_shortlisted: bool
    # The owner's inbox item and its version, so the dossier can triage the offer through the inbox
    # actions; both are null while the owner has no inbox item for the opportunity.
    job_inbox_item_id: int | None
    version: int | None


class HiringWeekRead(StrictModel):
    """New and open offers in one week."""

    week_start: date
    new_offers: int
    open_offers: int


class BoardRead(StrictModel):
    """A source that collects the company's offers, with the result of its last run."""

    source_configuration_id: int
    display_name: str
    enabled: bool
    url: str
    source_type: SourceType
    version: int
    # The latest run of this source (all null before its first run).
    last_outcome: SourceOutcome | None = None
    last_error_class: str | None = None
    last_finished_at: datetime | None = None
    last_collected_count: int | None = None
    # Postings the run read but did not keep: pages that are no postings and, for a board with
    # filters, those the owner's filters left out.
    last_dropped_count: int | None = None
    # Whether the owner's opt-in filters (ADR-051) are on for this company board.
    filters_enabled: bool = False


class CompanyDossierRead(StrictModel):
    """The company dossier."""

    company_id: int
    name: str
    homepage_url: str | None
    careers_url: str | None
    employer_type: str | None
    enriched_at: datetime | None
    stale: bool
    is_followed: bool
    is_ignored: bool
    facts: list[FactRead]
    candidates: list[CandidateRead]
    offers: list[OfferRead]
    offers_truncated: bool
    hiring: list[HiringWeekRead]
    boards: list[BoardRead]
    warnings: list[str]
