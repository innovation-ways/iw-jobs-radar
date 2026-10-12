"""API contracts for companies (document 07 and document 13, section 9)."""

from typing import Literal

from pydantic import Field

from jobs_radar.schemas.common import StrictModel


class CompanySummary(StrictModel):
    """A company with its counted offers (open, recent and not ignored; ADR-053)."""

    company_id: int
    name: str
    homepage_url: str | None
    careers_url: str | None
    employer_type: str | None
    open_offers: int
    recommended_offers: int
    best_fit_score: int | None
    pending_candidates: int
    is_followed: bool
    is_ignored: bool


class CompanyList(StrictModel):
    """A page of the company list."""

    items: list[CompanySummary]
    total: int
    sort: Literal["newest", "recommended", "fit", "name"]
    search_intent_id: int | None
    relevance_min_score: int
    recency_days: int


class CompanyFollowState(StrictModel):
    """Whether the owner follows a company (ADR-053)."""

    company_id: int
    is_followed: bool


class CompanyIgnoreState(StrictModel):
    """Whether the owner ignores a company (ADR-061)."""

    company_id: int
    is_ignored: bool


class CompanyWebsiteSet(StrictModel):
    """The company's own website, typed by the owner (ADR-054)."""

    url: str = Field(min_length=1, max_length=300)
