"""The company list with counted offers, best fit and follow state (document 13 s.9, ADR-053).

For every company: the *counted* offers (open, first seen within the recency limit and not ignored
by the owner), how many of them are recommended, the best fit among them, whether the owner follows
the company and how many identification candidates wait for a decision. A recommended offer is one
whose latest evaluation of the primary posting under the chosen intent has a fit at or above the
threshold and is not ``not_recommended``. Everything is computed in one grouped query so the list
scales with the number of companies, not offers.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import Select, and_, case, exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from jobs_radar.db.models import (
    Company,
    CompanyAlias,
    CompanyEnrichmentCandidate,
    CompanyFollow,
    CompanyIgnore,
    IntentRevision,
    JobInboxItem,
    JobOpportunity,
    JobSnapshot,
    MatchEvaluation,
)
from jobs_radar.domain.enums import InboxState, Recommendation

Sort = Literal["newest", "recommended", "fit", "name"]


@dataclass(frozen=True)
class CompanyRow:
    """One company with its counted offers."""

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
    latest_offer_at: datetime | None


@dataclass(frozen=True)
class CompanyPage:
    """A page of the list and the total number of matching companies."""

    rows: list[CompanyRow]
    total: int


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def latest_evaluation_join(search_intent_id: int | None) -> tuple[Any, Any]:
    """Return ``(evaluation alias, ON clause)`` for the latest evaluation under an intent.

    Without an intent the clause is false, so no offer has a fit.
    """
    evaluation = aliased(MatchEvaluation)
    if search_intent_id is None:
        return evaluation, literal(False)
    newer_snapshot = aliased(JobSnapshot)
    newer_evaluation = aliased(MatchEvaluation)
    latest_snapshot = (
        select(func.max(newer_snapshot.job_snapshot_id))
        .where(newer_snapshot.job_posting_id == JobOpportunity.primary_job_posting_id)
        .correlate(JobOpportunity)
        .scalar_subquery()
    )
    latest_evaluation = (
        select(func.max(newer_evaluation.match_evaluation_id))
        .join(
            IntentRevision,
            IntentRevision.intent_revision_id == newer_evaluation.intent_revision_id,
        )
        .where(
            newer_evaluation.job_snapshot_id == latest_snapshot,
            IntentRevision.search_intent_id == search_intent_id,
        )
        .correlate(JobOpportunity)
        .scalar_subquery()
    )
    return evaluation, evaluation.match_evaluation_id == latest_evaluation


def ignored_by(owner_id: int) -> Any:
    """Condition: the owner ignored the (correlated) opportunity."""
    return exists().where(
        JobInboxItem.owner_id == owner_id,
        JobInboxItem.job_opportunity_id == JobOpportunity.job_opportunity_id,
        JobInboxItem.state == InboxState.IGNORED.value,
    )


def set_aside_by(evaluation: Any, floor: int) -> Any:
    """Predicate: the latest evaluation is "Set aside" in the inbox (ADR-058, ADR-060).

    That is a ``not_recommended`` verdict or a fit below the owner's floor. A job without an
    evaluation has no verdict yet, so the predicate is never true for it (``coalesce``).
    """
    return func.coalesce(
        or_(
            evaluation.recommendation == Recommendation.NOT_RECOMMENDED.value,
            evaluation.fit_score < floor,
        ),
        False,
    )


class CompanyListQueries:
    """Reads the company list."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _stats(
        self,
        *,
        owner_id: int,
        now: datetime,
        recency_days: int,
        search: str | None,
        search_intent_id: int | None,
        relevance_min_score: int,
        set_aside_below: int,
    ) -> Select[Any]:
        evaluation, on_evaluation = latest_evaluation_join(search_intent_id)
        recommended: Any = and_(
            evaluation.fit_score >= relevance_min_score,
            evaluation.recommendation != Recommendation.NOT_RECOMMENDED.value,
        )
        # Old, closed and ignored offers are left out of the join so that the company stays in the
        # list with zero counted offers (a followed company must not disappear).
        counted = and_(
            JobOpportunity.company_id == Company.company_id,
            JobOpportunity.closed_at.is_(None),
            JobOpportunity.first_seen_at >= now - timedelta(days=recency_days),
            ~ignored_by(owner_id),
        )
        # The evaluation is joined after the opportunity, so the set-aside rule (same as the
        # inbox tab) is applied to the aggregates below instead of the join.
        kept: Any = ~set_aside_by(evaluation, set_aside_below)
        statement = (
            select(
                Company.company_id,
                Company.canonical_name.label("name"),
                Company.homepage_url,
                Company.careers_url,
                Company.employer_type,
                func.count(JobOpportunity.job_opportunity_id).filter(kept).label("open_offers"),
                func.count(JobOpportunity.job_opportunity_id)
                .filter(and_(kept, recommended))
                .label("recommended_offers"),
                func.max(evaluation.fit_score).filter(kept).label("best_fit_score"),
                func.max(JobOpportunity.first_seen_at).filter(kept).label("latest_offer_at"),
                select(func.count())
                .where(
                    CompanyEnrichmentCandidate.company_id == Company.company_id,
                    CompanyEnrichmentCandidate.status == "pending",
                )
                .correlate(Company)
                .scalar_subquery()
                .label("pending_candidates"),
                exists()
                .where(
                    CompanyFollow.owner_id == owner_id,
                    CompanyFollow.company_id == Company.company_id,
                )
                .label("is_followed"),
                exists()
                .where(
                    CompanyIgnore.owner_id == owner_id,
                    CompanyIgnore.company_id == Company.company_id,
                )
                .label("is_ignored"),
            )
            .select_from(Company)
            .outerjoin(JobOpportunity, counted)
            .outerjoin(evaluation, on_evaluation)
            .group_by(Company.company_id)
        )
        if search:
            pattern = f"%{_escape_like(search.strip().lower())}%"
            alias_match = (
                select(CompanyAlias.company_alias_id)
                .where(
                    CompanyAlias.company_id == Company.company_id,
                    CompanyAlias.alias_normalised.like(pattern, escape="\\"),
                )
                .exists()
            )
            statement = statement.where(
                or_(Company.name_normalised.like(pattern, escape="\\"), alias_match)
            )
        return statement

    async def page(
        self,
        *,
        owner_id: int,
        now: datetime,
        recency_days: int,
        search: str | None,
        search_intent_id: int | None,
        relevance_min_score: int,
        set_aside_below: int,
        sort: Sort,
        followed_only: bool,
        hide_ignored: bool,
        ignored_only: bool,
        open_only: bool,
        recommended_only: bool,
        pending_only: bool,
        limit: int,
        offset: int,
    ) -> CompanyPage:
        """Return one page of companies and the total that match.

        ``open_only`` keeps companies with counted offers *and* the followed ones: following is a
        promise to keep watching, so it never hides a company.
        """
        stats = self._stats(
            owner_id=owner_id,
            now=now,
            recency_days=recency_days,
            search=search,
            search_intent_id=search_intent_id,
            relevance_min_score=relevance_min_score,
            set_aside_below=set_aside_below,
        ).subquery()
        filtered = select(stats)
        if followed_only:
            filtered = filtered.where(stats.c.is_followed)
        if hide_ignored:
            filtered = filtered.where(~stats.c.is_ignored)
        if ignored_only:
            filtered = filtered.where(stats.c.is_ignored)
        if open_only:
            filtered = filtered.where(or_(stats.c.open_offers > 0, stats.c.is_followed))
        if recommended_only:
            filtered = filtered.where(stats.c.recommended_offers > 0)
        if pending_only:
            filtered = filtered.where(stats.c.pending_candidates > 0)
        orders: dict[str, list[Any]] = {
            "newest": [
                stats.c.latest_offer_at.desc().nulls_last(),
                stats.c.recommended_offers.desc(),
            ],
            "recommended": [
                stats.c.recommended_offers.desc(),
                stats.c.latest_offer_at.desc().nulls_last(),
            ],
            "fit": [stats.c.best_fit_score.desc().nulls_last(), stats.c.open_offers.desc()],
            "name": [],
        }
        order = [stats.c.is_followed.desc(), *orders[sort], stats.c.name]
        total = int(
            (
                await self._session.execute(select(func.count()).select_from(filtered.subquery()))
            ).scalar_one()
        )
        rows = (
            await self._session.execute(
                filtered.order_by(*order, stats.c.company_id).limit(limit).offset(offset)
            )
        ).all()
        return CompanyPage(
            rows=[CompanyRow(**dict(row._mapping)) for row in rows],
            total=total,
        )


@dataclass(frozen=True)
class OfferRow:
    """One opportunity of a company with its latest fit under the intent and the owner's state."""

    job_opportunity_id: int
    title: str
    source_url: str
    first_seen_at: datetime
    closed_at: datetime | None
    fit_score: int | None
    recommendation: str | None
    state: str | None
    is_shortlisted: bool
    job_inbox_item_id: int | None
    version: int | None

    @property
    def closed(self) -> bool:
        """Whether the opportunity is no longer listed."""
        return self.closed_at is not None


class CompanyDossierQueries:
    """Reads what the dossier shows besides the company row."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_followed(self, owner_id: int, company_id: int) -> bool:
        """Whether the owner follows the company."""
        found = await self._session.execute(
            select(CompanyFollow.company_follow_id).where(
                CompanyFollow.owner_id == owner_id, CompanyFollow.company_id == company_id
            )
        )
        return found.first() is not None

    async def is_ignored(self, owner_id: int, company_id: int) -> bool:
        """Whether the owner ignores the company (ADR-061)."""
        found = await self._session.execute(
            select(CompanyIgnore.company_ignore_id).where(
                CompanyIgnore.owner_id == owner_id, CompanyIgnore.company_id == company_id
            )
        )
        return found.first() is not None

    async def offers(
        self,
        owner_id: int,
        company_id: int,
        search_intent_id: int | None,
        limit: int,
        *,
        not_before: datetime | None,
        set_aside_below: int = 0,
    ) -> list[OfferRow]:
        """Return the company's opportunities: actionable ones first, then best fit, then newest.

        Ignored and closed opportunities sort last, so that when ``limit`` cuts the list they are
        the ones left out: the cut must never hide offers the owner can still act on.

        ``not_before`` leaves out opportunities first seen earlier than that time (``None`` keeps
        all). Each row carries the owner's inbox state so the screen can dim ignored offers.
        Offers the inbox lists under "Set aside" (``not_recommended`` or a fit below
        ``set_aside_below``) are left out, as they are in the counts of the company list.
        """
        from jobs_radar.db.models import JobPosting  # local: keeps the module header small

        evaluation, on_evaluation = latest_evaluation_join(search_intent_id)
        statement = (
            select(
                JobOpportunity.job_opportunity_id,
                JobPosting.title,
                JobPosting.source_url,
                JobOpportunity.first_seen_at,
                JobOpportunity.closed_at,
                evaluation.fit_score,
                evaluation.recommendation,
                JobInboxItem.state,
                func.coalesce(JobInboxItem.is_shortlisted, False),
                JobInboxItem.job_inbox_item_id,
                JobInboxItem.version,
            )
            .select_from(JobOpportunity)
            .join(JobPosting, JobPosting.job_posting_id == JobOpportunity.primary_job_posting_id)
            .outerjoin(evaluation, on_evaluation)
            .outerjoin(
                JobInboxItem,
                and_(
                    JobInboxItem.job_opportunity_id == JobOpportunity.job_opportunity_id,
                    JobInboxItem.owner_id == owner_id,
                ),
            )
            .where(
                JobOpportunity.company_id == company_id,
                ~set_aside_by(evaluation, set_aside_below),
            )
        )
        if not_before is not None:
            statement = statement.where(JobOpportunity.first_seen_at >= not_before)
        rows = await self._session.execute(
            statement.order_by(
                case(
                    (JobInboxItem.state == InboxState.IGNORED.value, 1),
                    (JobOpportunity.closed_at.is_not(None), 1),
                    else_=0,
                ),
                evaluation.fit_score.desc().nulls_last(),
                JobOpportunity.first_seen_at.desc(),
                JobOpportunity.job_opportunity_id.desc(),
            ).limit(limit)
        )
        return [OfferRow(*row) for row in rows.all()]

    async def lifespans(self, company_id: int) -> list[tuple[datetime, datetime | None]]:
        """Return ``(first_seen_at, closed_at)`` of every opportunity of the company."""
        rows = await self._session.execute(
            select(JobOpportunity.first_seen_at, JobOpportunity.closed_at).where(
                JobOpportunity.company_id == company_id
            )
        )
        return [(first, closed) for first, closed in rows.all()]
