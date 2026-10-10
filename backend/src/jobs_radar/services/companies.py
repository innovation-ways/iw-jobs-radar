"""Company list and dossiers (T7). The caller owns the transaction."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import (
    Company,
    CompanyEnrichmentCandidate,
    CompanyFact,
    SourceConfiguration,
)
from jobs_radar.repositories.companies import CompanyFollowRepository
from jobs_radar.repositories.company_list import (
    CompanyDossierQueries,
    CompanyListQueries,
    CompanyPage,
    OfferRow,
    Sort,
)
from jobs_radar.repositories.schedule import ScheduleRepository

Clock = Callable[[], datetime]
# Default minimum fit for an offer to count as relevant (document 13, section 11.2).
DEFAULT_RELEVANCE_MIN_SCORE = 45
REFRESH_AFTER = timedelta(days=30)
HIRING_WEEKS = 12
OFFER_LIMIT = 50


@dataclass(frozen=True)
class FactView:
    """A current fact with its provenance."""

    fact_key: str
    value: Any
    origin: str
    source_name: str
    source_url: str | None
    retrieved_at: datetime
    licence: str | None
    confidence: float | None


@dataclass(frozen=True)
class HiringWeek:
    """New and open offers in one week (weeks start on Monday, UTC)."""

    week_start: date
    new_offers: int
    open_offers: int


@dataclass(frozen=True)
class Dossier:
    """Everything the company dossier shows."""

    company: Company
    facts: list[FactView]
    candidates: list[CompanyEnrichmentCandidate]
    offers: list[OfferRow]
    hiring: list[HiringWeek]
    boards: list[SourceConfiguration]
    stale: bool
    is_followed: bool
    offers_truncated: bool


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CompanyService:
    """Use cases around companies."""

    def __init__(self, session: AsyncSession, *, clock: Clock = _utc_now) -> None:
        self._session = session
        self._queries = CompanyListQueries(session)
        self._dossier = CompanyDossierQueries(session)
        self._follows = CompanyFollowRepository(session)
        self._schedule = ScheduleRepository(session)
        self._clock = clock

    async def list_companies(
        self,
        owner_id: int,
        *,
        q: str | None = None,
        sort: Sort = "fit",
        search_intent_id: int | None = None,
        relevance_min_score: int = DEFAULT_RELEVANCE_MIN_SCORE,
        followed_only: bool = False,
        open_only: bool = False,
        recommended_only: bool = False,
        pending_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> CompanyPage:
        """Return companies with counted offers; followed ones come first (ADR-053).

        Only open offers first seen within the owner's recency limit and not ignored are counted.
        """
        return await self._queries.page(
            owner_id=owner_id,
            now=self._clock(),
            recency_days=await self._schedule.company_recency_days(owner_id),
            search=q,
            search_intent_id=search_intent_id,
            relevance_min_score=relevance_min_score,
            sort=sort,
            followed_only=followed_only,
            open_only=open_only,
            recommended_only=recommended_only,
            pending_only=pending_only,
            limit=limit,
            offset=offset,
        )

    async def set_followed(self, owner_id: int, company_id: int, *, followed: bool) -> None:
        """Follow or unfollow a company; repeating the same call changes nothing.

        Raises:
            NotFoundError: the company does not exist.
        """
        if await self._session.get(Company, company_id) is None:
            msg = f"Company {company_id} does not exist."
            raise NotFoundError(msg)
        if followed:
            await self._follows.follow(owner_id, company_id)
        else:
            await self._follows.unfollow(owner_id, company_id)

    async def dossier(
        self,
        owner_id: int,
        company_id: int,
        *,
        search_intent_id: int | None,
        include_older: bool = False,
    ) -> Dossier:
        """Return the company with its current facts, candidates, offers and hiring series.

        Offers first seen before the owner's recency limit are left out unless ``include_older``.
        """
        company = await self._session.get(Company, company_id)
        if company is None:
            msg = f"Company {company_id} does not exist."
            raise NotFoundError(msg)
        now = self._clock()
        facts = (
            await self._session.execute(
                select(CompanyFact)
                .where(CompanyFact.company_id == company_id, CompanyFact.superseded_at.is_(None))
                .order_by(CompanyFact.fact_key)
            )
        ).scalars()
        candidates = (
            await self._session.execute(
                select(CompanyEnrichmentCandidate)
                .where(
                    CompanyEnrichmentCandidate.company_id == company_id,
                    CompanyEnrichmentCandidate.status == "pending",
                )
                .order_by(CompanyEnrichmentCandidate.company_enrichment_candidate_id)
            )
        ).scalars()
        boards = (
            await self._session.execute(
                select(SourceConfiguration)
                .where(SourceConfiguration.company_id == company_id)
                .order_by(SourceConfiguration.source_configuration_id)
            )
        ).scalars()
        # One more than the limit tells whether the list was cut.
        offers = await self._dossier.offers(
            owner_id,
            company_id,
            search_intent_id,
            OFFER_LIMIT + 1,
            not_before=None
            if include_older
            else now - timedelta(days=await self._schedule.company_recency_days(owner_id)),
        )
        return Dossier(
            company=company,
            facts=[
                FactView(
                    f.fact_key,
                    f.value_json,
                    f.origin,
                    f.source_name,
                    f.source_url,
                    f.retrieved_at,
                    f.licence,
                    float(f.confidence) if f.confidence is not None else None,
                )
                for f in facts
            ],
            candidates=list(candidates),
            offers=offers[:OFFER_LIMIT],
            offers_truncated=len(offers) > OFFER_LIMIT,
            is_followed=await self._dossier.is_followed(owner_id, company_id),
            hiring=self._hiring(await self._dossier.lifespans(company_id), now),
            boards=list(boards),
            stale=company.enriched_at is None or now - company.enriched_at > REFRESH_AFTER,
        )

    @staticmethod
    def _hiring(spans: list[tuple[datetime, datetime | None]], now: datetime) -> list[HiringWeek]:
        """Weekly new and open offers for the last 12 weeks, oldest first."""
        monday = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        weeks = []
        for n in range(HIRING_WEEKS - 1, -1, -1):
            start = monday - timedelta(weeks=n)
            end = min(start + timedelta(days=7), now)
            weeks.append(
                HiringWeek(
                    week_start=start.date(),
                    new_offers=sum(
                        1 for first, _ in spans if start <= first < start + timedelta(days=7)
                    ),
                    open_offers=sum(
                        1
                        for first, closed in spans
                        if first <= end and (closed is None or closed > end)
                    ),
                )
            )
        return weeks
