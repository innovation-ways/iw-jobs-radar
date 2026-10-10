"""API contracts for the company dossier (document 07, document 13 section 9)."""

from datetime import date, datetime
from typing import Any, Literal

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


class HiringWeekRead(StrictModel):
    """New and open offers in one week."""

    week_start: date
    new_offers: int
    open_offers: int


class BoardRead(StrictModel):
    """A job board of the company."""

    source_configuration_id: int
    display_name: str
    enabled: bool
    url: str


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
    facts: list[FactRead]
    candidates: list[CandidateRead]
    offers: list[OfferRead]
    hiring: list[HiringWeekRead]
    boards: list[BoardRead]
    warnings: list[str]
