"""API contracts for companies (document 07 and document 13, section 9)."""

from typing import Literal

from jobs_radar.schemas.common import StrictModel


class CompanySummary(StrictModel):
    """A company with its offer counts."""

    company_id: int
    name: str
    homepage_url: str | None
    careers_url: str | None
    employer_type: str | None
    open_offers: int
    new_offers_7d: int
    new_offers_15d: int
    new_offers_30d: int
    relevant_new_offers_7d: int
    relevant_new_offers_15d: int
    relevant_new_offers_30d: int


class CompanyList(StrictModel):
    """A page of the company list."""

    items: list[CompanySummary]
    total: int
    window: int
    sort: Literal["new", "relevant", "open", "name"]
    search_intent_id: int | None
    relevance_min_score: int
