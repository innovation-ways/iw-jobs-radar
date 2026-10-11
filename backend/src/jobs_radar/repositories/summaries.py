"""Data access for the stored job summaries (ADR-059)."""

from datetime import datetime

from sqlalchemy import exists, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from jobs_radar.db.models import JobPosting, JobSnapshot, JobSummary
from jobs_radar.domain.enums import SummaryStatus


class SummaryRepository:
    """Reads and writes ``job_summary`` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def latest_snapshot_id(self, job_posting_id: int) -> int | None:
        """Return the id of the newest snapshot of the posting, if it has one."""
        found = (
            await self._session.execute(
                select(func.max(JobSnapshot.job_snapshot_id)).where(
                    JobSnapshot.job_posting_id == job_posting_id
                )
            )
        ).scalar_one_or_none()
        return None if found is None else int(found)

    async def latest_success(
        self,
        job_snapshot_id: int,
        *,
        provider: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
    ) -> JobSummary | None:
        """Return the newest successful summary of the snapshot.

        With ``provider`` and ``model`` only that model's summary counts; with ``prompt_version``
        only that prompt's (a new prompt must write its summaries again).
        """
        statement = (
            select(JobSummary)
            .where(
                JobSummary.job_snapshot_id == job_snapshot_id,
                JobSummary.status == SummaryStatus.SUCCEEDED.value,
            )
            .order_by(JobSummary.job_summary_id.desc())
            .limit(1)
        )
        if provider is not None and model is not None:
            statement = statement.where(JobSummary.provider == provider, JobSummary.model == model)
        if prompt_version is not None:
            statement = statement.where(JobSummary.prompt_version == prompt_version)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def add(
        self,
        *,
        job_snapshot_id: int,
        provider: str,
        model: str,
        prompt_version: str,
        status: SummaryStatus,
        summary_text: str | None,
        error_class: str | None,
        latency_ms: int | None,
    ) -> bool:
        """Store an attempt; return ``False`` if the same successful summary already exists."""
        statement = (
            insert(JobSummary)
            .values(
                job_snapshot_id=job_snapshot_id,
                provider=provider,
                model=model,
                prompt_version=prompt_version,
                status=status.value,
                summary_text=summary_text,
                error_class=error_class,
                latency_ms=latency_ms,
            )
            .on_conflict_do_nothing(
                index_elements=["job_snapshot_id", "provider", "model", "prompt_version"],
                # A literal, not a bound value: once the driver prepares the statement (after a
                # few runs) PostgreSQL cannot match a parameterised predicate to the partial
                # index. It must equal the index predicate in migration 0016.
                index_where=text("status = 'succeeded'"),
            )
            .returning(JobSummary.job_summary_id)
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def pending(self, prompt_version: str, since: datetime, limit: int) -> list[int]:
        """Return posting ids still to summarise, newest jobs first.

        Only open postings first seen at or after ``since`` count, judged by their latest
        snapshot; a job with any attempt (good or failed, any model) for the prompt is done, so a
        failed one waits for the owner to ask.
        """
        newer = aliased(JobSnapshot)
        latest_snapshot = (
            select(func.max(newer.job_snapshot_id))
            .where(newer.job_posting_id == JobPosting.job_posting_id)
            .correlate(JobPosting)
            .scalar_subquery()
        )
        # Correlated explicitly: left alone, the EXISTS would add its own copy of the posting.
        attempted = (
            exists()
            .where(
                JobSummary.job_snapshot_id == latest_snapshot,
                JobSummary.prompt_version == prompt_version,
            )
            .correlate(JobPosting)
        )
        statement = (
            select(JobPosting.job_posting_id)
            .where(
                JobPosting.closed_at.is_(None),
                JobPosting.first_seen_at >= since,
                latest_snapshot.is_not(None),
                ~attempted,
            )
            .order_by(JobPosting.first_seen_at.desc(), JobPosting.job_posting_id.desc())
            .limit(limit)
        )
        return [int(i) for i in (await self._session.execute(statement)).scalars()]
