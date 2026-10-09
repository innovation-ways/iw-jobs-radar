"""Read-only counts behind the pipeline status: open jobs, analysed, scored, failed, recent work."""

from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from jobs_radar.db.models import JobExtraction, JobPosting, JobSnapshot, MatchEvaluation


class PipelineRepository:
    """Counts the work of the extraction queue and of scoring (no writes)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _latest_open_snapshots(self) -> Any:
        """Select the id of the latest snapshot of every open posting."""
        newer = aliased(JobSnapshot)
        snapshot = aliased(JobSnapshot)
        statement = (
            select(snapshot.job_snapshot_id)
            .join(JobPosting, JobPosting.job_posting_id == snapshot.job_posting_id)
            .where(
                JobPosting.closed_at.is_(None),
                snapshot.job_snapshot_id
                == select(func.max(newer.job_snapshot_id))
                .where(newer.job_posting_id == snapshot.job_posting_id)
                .scalar_subquery(),
            )
        )
        return statement

    async def analysis_counts(
        self, *, provider: str | None, model: str | None, prompt_version: str
    ) -> tuple[int, int, int]:
        """Return ``(open jobs, analysed, failed)`` for the latest snapshots of open postings.

        With a provider and model only extractions by them count (a new model re-queues the same
        job); without them (No AI) any successful extraction counts.
        """
        statement = self._latest_open_snapshots()
        open_jobs = (
            await self._session.execute(select(func.count()).select_from(statement.subquery()))
        ).scalar_one()

        async def with_status(status: str) -> int:
            conditions = [
                JobExtraction.job_snapshot_id.in_(statement),
                JobExtraction.status == status,
            ]
            if provider is not None and model is not None:
                conditions += [
                    JobExtraction.provider == provider,
                    JobExtraction.model == model,
                    JobExtraction.prompt_version == prompt_version,
                ]
            # One job counts once even if it was extracted by several attempts or taxonomies.
            return int(
                (
                    await self._session.execute(
                        select(func.count(func.distinct(JobExtraction.job_snapshot_id))).where(
                            and_(*conditions)
                        )
                    )
                ).scalar_one()
            )

        return int(open_jobs), await with_status("succeeded"), await with_status("failed")

    async def last_failure(
        self, *, provider: str | None, model: str | None
    ) -> tuple[str | None, datetime | None]:
        """Return the reason and time of the newest failed extraction of the current model."""
        statement = select(JobExtraction.error_class, JobExtraction.completed_at).where(
            JobExtraction.status == "failed"
        )
        if provider is not None and model is not None:
            statement = statement.where(
                JobExtraction.provider == provider, JobExtraction.model == model
            )
        row = (
            await self._session.execute(
                statement.order_by(JobExtraction.completed_at.desc().nulls_last()).limit(1)
            )
        ).first()
        return (row[0], row[1]) if row else (None, None)

    async def completed_since(self, since: datetime) -> tuple[int, int]:
        """Return ``(extractions succeeded, evaluations created)`` since ``since``."""
        analysed = (
            await self._session.execute(
                select(func.count()).where(
                    JobExtraction.status == "succeeded", JobExtraction.completed_at >= since
                )
            )
        ).scalar_one()
        scored = (
            await self._session.execute(
                select(func.count()).where(MatchEvaluation.created_at >= since)
            )
        ).scalar_one()
        return int(analysed), int(scored)
