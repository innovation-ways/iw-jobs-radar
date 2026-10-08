"""Data access for opportunities and the links between postings and opportunities (ADR-023)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import (
    JobOpportunity,
    JobOpportunityLink,
    JobPosting,
    JobSnapshot,
)


@dataclass(frozen=True)
class Candidate:
    """A posting of the same company on another source, with the opportunity it belongs to."""

    posting: JobPosting
    snapshot: JobSnapshot
    job_opportunity_id: int


class DedupRepository:
    """Reads and writes ``job_opportunity`` and ``job_opportunity_link`` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def unlinked_postings(self, limit: int) -> list[JobPosting]:
        """Open postings that belong to no opportunity yet, newest first."""
        linked = (
            select(JobOpportunityLink.job_posting_id)
            .where(JobOpportunityLink.state != "rejected")
            .where(JobOpportunityLink.job_posting_id == JobPosting.job_posting_id)
            .exists()
        )
        rows = await self._session.execute(
            select(JobPosting)
            .where(JobPosting.closed_at.is_(None), ~linked)
            .order_by(JobPosting.first_seen_at.desc(), JobPosting.job_posting_id.desc())
            .limit(limit)
        )
        return list(rows.scalars())

    async def get_posting(self, job_posting_id: int) -> JobPosting:
        """Return a posting; ``NotFoundError`` if it does not exist."""
        posting = await self._session.get(JobPosting, job_posting_id)
        if posting is None:
            msg = "Job posting not found."
            raise NotFoundError(msg)
        return posting

    async def active_link(self, job_posting_id: int) -> JobOpportunityLink | None:
        """Return the posting's current (not rejected) link, if any."""
        return (
            await self._session.execute(
                select(JobOpportunityLink).where(
                    JobOpportunityLink.job_posting_id == job_posting_id,
                    JobOpportunityLink.state != "rejected",
                )
            )
        ).scalar_one_or_none()

    async def latest_snapshot(self, job_posting_id: int) -> JobSnapshot:
        """Return the posting's latest snapshot."""
        return (
            await self._session.execute(
                select(JobSnapshot)
                .where(JobSnapshot.job_posting_id == job_posting_id)
                .order_by(JobSnapshot.job_snapshot_id.desc())
                .limit(1)
            )
        ).scalar_one()

    async def candidates(self, posting: JobPosting) -> list[Candidate]:
        """Open postings of the same company on other sources, each with its opportunity."""
        rows = await self._session.execute(
            select(JobPosting, JobOpportunityLink.job_opportunity_id)
            .join(
                JobOpportunityLink, JobOpportunityLink.job_posting_id == JobPosting.job_posting_id
            )
            .where(
                JobOpportunityLink.state != "rejected",
                JobPosting.company_id == posting.company_id,
                JobPosting.source_configuration_id != posting.source_configuration_id,
                JobPosting.closed_at.is_(None),
                JobPosting.job_posting_id != posting.job_posting_id,
            )
            .order_by(JobPosting.job_posting_id)
        )
        found: list[Candidate] = []
        for candidate, opportunity_id in rows.all():
            snapshot = await self.latest_snapshot(candidate.job_posting_id)
            found.append(Candidate(candidate, snapshot, int(opportunity_id)))
        return found

    async def rejected_opportunity_ids(self, job_posting_id: int) -> set[int]:
        """Opportunities the owner already said this posting does not belong to."""
        rows = await self._session.execute(
            select(JobOpportunityLink.job_opportunity_id).where(
                JobOpportunityLink.job_posting_id == job_posting_id,
                JobOpportunityLink.state == "rejected",
            )
        )
        return {int(item) for item in rows.scalars()}

    async def create_opportunity(self, posting: JobPosting) -> JobOpportunity:
        """Create an opportunity whose only listing is ``posting``."""
        opportunity = JobOpportunity(
            company_id=posting.company_id,
            primary_job_posting_id=posting.job_posting_id,
            first_seen_at=posting.first_seen_at,
            last_seen_at=posting.last_seen_at,
            closed_at=posting.closed_at,
        )
        self._session.add(opportunity)
        await self._session.flush()
        return opportunity

    async def add_link(
        self,
        *,
        job_opportunity_id: int,
        job_posting_id: int,
        state: str,
        similarity: float,
        features: dict[str, Any],
        method: str,
    ) -> JobOpportunityLink:
        """Link a posting to an opportunity."""
        link = JobOpportunityLink(
            job_opportunity_id=job_opportunity_id,
            job_posting_id=job_posting_id,
            state=state,
            similarity=Decimal(str(round(similarity, 4))),
            features_json=features,
            method=method,
        )
        self._session.add(link)
        await self._session.flush()
        return link

    async def get_link(self, job_opportunity_link_id: int) -> JobOpportunityLink:
        """Return a link; ``NotFoundError`` if it does not exist."""
        link = await self._session.get(JobOpportunityLink, job_opportunity_link_id)
        if link is None:
            msg = "Opportunity link not found."
            raise NotFoundError(msg)
        return link

    async def opportunity(self, job_opportunity_id: int) -> JobOpportunity:
        """Return an opportunity."""
        opportunity = await self._session.get(JobOpportunity, job_opportunity_id)
        if opportunity is None:
            msg = "Opportunity not found."
            raise NotFoundError(msg)
        return opportunity

    async def postings_of(self, job_opportunity_id: int) -> list[JobPosting]:
        """Return the postings currently grouped under an opportunity."""
        rows = await self._session.execute(
            select(JobPosting)
            .join(
                JobOpportunityLink, JobOpportunityLink.job_posting_id == JobPosting.job_posting_id
            )
            .where(
                JobOpportunityLink.job_opportunity_id == job_opportunity_id,
                JobOpportunityLink.state != "rejected",
            )
            .order_by(JobPosting.job_posting_id)
        )
        return list(rows.scalars())

    async def count_postings(self, job_opportunity_id: int) -> int:
        """Count the postings currently grouped under an opportunity."""
        return int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(JobOpportunityLink)
                    .where(
                        JobOpportunityLink.job_opportunity_id == job_opportunity_id,
                        JobOpportunityLink.state != "rejected",
                    )
                )
            ).scalar_one()
        )

    async def update_aggregates(
        self,
        opportunity: JobOpportunity,
        *,
        primary: int,
        first_seen_at: datetime,
        last_seen_at: datetime,
        closed_at: datetime | None,
    ) -> None:
        """Store the recomputed summary of an opportunity."""
        opportunity.primary_job_posting_id = primary
        opportunity.first_seen_at = first_seen_at
        opportunity.last_seen_at = last_seen_at
        opportunity.closed_at = closed_at
        await self._session.flush()
