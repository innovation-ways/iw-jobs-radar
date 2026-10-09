"""Data access for the AI extraction queue (``job_extraction``; document 13, section 6.3).

Rows are queued as ``pending`` and finalised exactly once (``succeeded`` or ``failed``); the
database then makes them immutable (ADR-041). Workers claim rows with ``FOR UPDATE SKIP LOCKED``.
"""

from collections.abc import Collection
from datetime import datetime
from typing import Any

from sqlalchemy import func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from jobs_radar.db.models import JobExtraction, JobPosting, JobSnapshot, TaxonomyVersion


class ExtractionRepository:
    """Reads and writes ``job_extraction`` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def current_taxonomy_version_id(self) -> int:
        """Return the id of the latest taxonomy version."""
        value = (
            await self._session.execute(select(func.max(TaxonomyVersion.taxonomy_version_id)))
        ).scalar_one()
        return int(value)

    async def enqueue_missing(
        self,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        taxonomy_version_id: int,
        limit: int,
    ) -> int:
        """Queue the latest snapshot of every open posting that has no extraction yet.

        "Yet" means for this provider, model, prompt version and taxonomy version, so a new model
        or prompt re-queues the same snapshot. Newest postings are queued first.
        """
        newer = aliased(JobSnapshot)
        latest = (
            select(func.max(newer.job_snapshot_id))
            .where(newer.job_posting_id == JobSnapshot.job_posting_id)
            .scalar_subquery()
        )
        already = (
            select(JobExtraction.job_extraction_id)
            .where(
                JobExtraction.job_snapshot_id == JobSnapshot.job_snapshot_id,
                JobExtraction.provider == provider,
                JobExtraction.model == model,
                JobExtraction.prompt_version == prompt_version,
                JobExtraction.taxonomy_version_id == taxonomy_version_id,
            )
            .exists()
        )
        candidates = (
            select(
                JobSnapshot.job_snapshot_id,
                literal("pending"),
                literal(provider),
                literal(model),
                literal(prompt_version),
                literal(taxonomy_version_id),
                literal(False),
                literal(0),
            )
            .join(JobPosting, JobPosting.job_posting_id == JobSnapshot.job_posting_id)
            .where(
                JobPosting.closed_at.is_(None),
                JobSnapshot.job_snapshot_id == latest,
                ~already,
            )
            .order_by(JobPosting.first_seen_at.desc(), JobSnapshot.job_snapshot_id.desc())
            .limit(limit)
        )
        statement = (
            insert(JobExtraction)
            .from_select(
                [
                    "job_snapshot_id",
                    "status",
                    "provider",
                    "model",
                    "prompt_version",
                    "taxonomy_version_id",
                    "truncated",
                    "attempts",
                ],
                candidates,
            )
            .on_conflict_do_nothing()
            .returning(JobExtraction.job_extraction_id)
        )
        # rowcount is not reliable for INSERT ... SELECT here, so count the returned ids.
        return len((await self._session.execute(statement)).all())

    async def claim_next(
        self,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        now: datetime,
        stale_before: datetime,
        exclude: Collection[int] = (),
    ) -> tuple[JobExtraction, JobSnapshot] | None:
        """Claim the next waiting extraction for this provider and model, with its snapshot.

        A row claimed by a worker that died (claim older than ``stale_before``) is reclaimed.
        """
        statement = (
            select(JobExtraction, JobSnapshot)
            .join(JobSnapshot, JobSnapshot.job_snapshot_id == JobExtraction.job_snapshot_id)
            .where(
                JobExtraction.status == "pending",
                JobExtraction.provider == provider,
                JobExtraction.model == model,
                JobExtraction.prompt_version == prompt_version,
                (JobExtraction.claimed_at.is_(None)) | (JobExtraction.claimed_at < stale_before),
            )
            .order_by(JobExtraction.job_extraction_id)
            .limit(1)
            .with_for_update(of=JobExtraction, skip_locked=True)
        )
        if exclude:
            statement = statement.where(JobExtraction.job_extraction_id.not_in(exclude))
        row = (await self._session.execute(statement)).first()
        if row is None:
            return None
        extraction, snapshot = row
        extraction.claimed_at = now
        await self._session.flush()
        return extraction, snapshot

    async def get(self, job_extraction_id: int) -> JobExtraction:
        """Return one extraction row (locked for the update that follows)."""
        extraction = (
            await self._session.execute(
                select(JobExtraction)
                .where(JobExtraction.job_extraction_id == job_extraction_id)
                .with_for_update()
            )
        ).scalar_one()
        return extraction

    async def release(self, extraction: JobExtraction, error_class: str | None) -> None:
        """Give the row back to the queue (no attempt used) and remember why it waited."""
        extraction.claimed_at = None
        extraction.error_class = error_class
        await self._session.flush()

    async def record_attempt(
        self,
        extraction: JobExtraction,
        *,
        error_class: str,
        now: datetime,
        max_attempts: int,
        detail: dict[str, Any] | None = None,
    ) -> bool:
        """Count a failed attempt; finalise as ``failed`` when attempts run out. Returns that."""
        extraction.attempts += 1
        extraction.error_class = error_class
        extraction.failure_json = detail
        extraction.claimed_at = None
        final = extraction.attempts >= max_attempts
        if final:
            extraction.status = "failed"
            extraction.completed_at = now
        await self._session.flush()
        return final

    async def finalise_success(
        self,
        extraction: JobExtraction,
        *,
        attributes: dict[str, Any],
        truncated: bool,
        latency_ms: int,
        now: datetime,
    ) -> None:
        """Store the result and make the row final."""
        extraction.status = "succeeded"
        extraction.attributes_json = attributes
        extraction.truncated = truncated
        extraction.latency_ms = latency_ms
        extraction.error_class = None
        extraction.attempts += 1
        extraction.claimed_at = None
        extraction.completed_at = now
        await self._session.flush()
