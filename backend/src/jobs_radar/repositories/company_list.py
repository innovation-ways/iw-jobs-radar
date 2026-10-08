"""The company list with new-offer counts per window (document 13, section 9).

For every company: open offers, opportunities first seen in the last 7, 15 and 30 days, and the
subset that is *relevant*: the latest evaluation of the opportunity's primary posting under the
chosen intent has a fit at or above the threshold and is not ``not_recommended``. Everything is
computed in one grouped query so the list scales with the number of companies, not offers.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import Select, and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from jobs_radar.db.models import (
    Company,
    CompanyAlias,
    IntentRevision,
    JobOpportunity,
    JobSnapshot,
    MatchEvaluation,
)
from jobs_radar.domain.enums import Recommendation

WINDOWS = (7, 15, 30)
Sort = Literal["new", "relevant", "open", "name"]


@dataclass(frozen=True)
class CompanyRow:
    """One company with its offer counts."""

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


@dataclass(frozen=True)
class CompanyPage:
    """A page of the list and the total number of matching companies."""

    rows: list[CompanyRow]
    total: int


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class CompanyListQueries:
    """Reads the company list."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _stats(
        self,
        *,
        now: datetime,
        search: str | None,
        search_intent_id: int | None,
        relevance_min_score: int,
    ) -> Select[Any]:
        evaluation = aliased(MatchEvaluation)
        newer_snapshot = aliased(JobSnapshot)
        newer_evaluation = aliased(MatchEvaluation)
        if search_intent_id is None:
            relevant: Any = literal(False)
            on_evaluation: Any = literal(False)
        else:
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
            on_evaluation = evaluation.match_evaluation_id == latest_evaluation
            relevant = and_(
                evaluation.fit_score >= relevance_min_score,
                evaluation.recommendation != Recommendation.NOT_RECOMMENDED.value,
            )

        columns: list[Any] = [
            Company.company_id,
            Company.canonical_name.label("name"),
            Company.homepage_url,
            Company.careers_url,
            Company.employer_type,
            func.count(JobOpportunity.job_opportunity_id)
            .filter(JobOpportunity.closed_at.is_(None))
            .label("open_offers"),
        ]
        for days in WINDOWS:
            recent = JobOpportunity.first_seen_at >= now - timedelta(days=days)
            columns.append(
                func.count(JobOpportunity.job_opportunity_id)
                .filter(recent)
                .label(f"new_offers_{days}d")
            )
        for days in WINDOWS:
            recent = JobOpportunity.first_seen_at >= now - timedelta(days=days)
            columns.append(
                func.count(JobOpportunity.job_opportunity_id)
                .filter(and_(recent, relevant))
                .label(f"relevant_new_offers_{days}d")
            )
        statement = (
            select(*columns)
            .select_from(Company)
            .outerjoin(JobOpportunity, JobOpportunity.company_id == Company.company_id)
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
        now: datetime,
        search: str | None,
        search_intent_id: int | None,
        relevance_min_score: int,
        window: int,
        sort: Sort,
        relevant_only: bool,
        limit: int,
        offset: int,
    ) -> CompanyPage:
        """Return one page of companies and the total that match."""
        stats = self._stats(
            now=now,
            search=search,
            search_intent_id=search_intent_id,
            relevance_min_score=relevance_min_score,
        ).subquery()
        relevant_column = stats.c[f"relevant_new_offers_{window}d"]
        new_column = stats.c[f"new_offers_{window}d"]
        filtered = select(stats)
        if relevant_only:
            filtered = filtered.where(relevant_column > 0)
        orders: dict[str, list[Any]] = {
            "new": [new_column.desc(), stats.c.name],
            "relevant": [relevant_column.desc(), new_column.desc(), stats.c.name],
            "open": [stats.c.open_offers.desc(), stats.c.name],
            "name": [stats.c.name],
        }
        order = orders[sort]
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
