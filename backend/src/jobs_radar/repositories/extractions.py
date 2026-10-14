"""Data access for the AI extraction queue (``job_extraction``; document 13, section 6.3).

Rows are queued as ``pending`` and finalised exactly once (``succeeded`` or ``failed``); the
database then makes them immutable (ADR-041). Workers claim rows with ``FOR UPDATE SKIP LOCKED``.
"""

from collections.abc import Collection
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from jobs_radar.db.models import (
    JobExtraction,
    JobInboxItem,
    JobOpportunityLink,
    JobPosting,
    JobSnapshot,
    MatchEvaluation,
    TaxonomyVersion,
)
from jobs_radar.domain.enums import InboxState


def _set_aside(snapshot: Any, *, below: int) -> Any:
    """Whether the main inbox sets the snapshot's opportunity aside (the same rule as the inbox).

    Set aside = the latest evaluation of the snapshot is not recommended, or its fit is below the
    owner's floor and the source has not changed the job since (ADR-058, ADR-060); a job without
    an evaluation is never set aside. ``below`` 0 turns the floor off.
    """
    newer = aliased(MatchEvaluation)
    latest = (
        select(func.max(newer.match_evaluation_id))
        .where(newer.job_snapshot_id == snapshot.job_snapshot_id)
        # Correlate to the snapshot of the enclosing query, or the maximum would be global.
        .correlate_except(newer)
        .scalar_subquery()
    )
    return (
        select(MatchEvaluation.match_evaluation_id)
        .select_from(MatchEvaluation)
        .join(JobOpportunityLink, JobOpportunityLink.job_posting_id == snapshot.job_posting_id)
        .join(
            JobInboxItem,
            JobInboxItem.job_opportunity_id == JobOpportunityLink.job_opportunity_id,
        )
        .where(
            MatchEvaluation.match_evaluation_id == latest,
            MatchEvaluation.job_snapshot_id == snapshot.job_snapshot_id,
            JobOpportunityLink.state != "rejected",
            or_(
                MatchEvaluation.recommendation == "not_recommended",
                and_(
                    JobInboxItem.state != InboxState.UPDATED_UNREAD.value,
                    MatchEvaluation.fit_score < below,
                ),
            ),
        )
        .exists()
    )


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
        accepted_prompt_versions: Collection[str] = (),
        set_aside_below: int = 0,
    ) -> int:
        """Queue the latest snapshot of every open posting that has no extraction yet.

        "Yet" means for this provider, model, prompt version and taxonomy version, so a new model
        or prompt re-queues the same snapshot, except when the snapshot already has a successful
        extraction of one of ``accepted_prompt_versions`` (same provider, model and taxonomy).
        A snapshot that already has a successful extraction of any version is not queued again
        once the owner has ignored or archived its opportunity, so a new prompt or taxonomy does
        not spend model time on jobs put away (ADR-073); the same holds for jobs the main inbox
        sets aside (``set_aside_below`` is the owner's low-fit floor). A snapshot with no
        successful extraction is always queued. Newest postings are queued first.
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
                JobExtraction.taxonomy_version_id == taxonomy_version_id,
                or_(
                    JobExtraction.prompt_version == prompt_version,
                    and_(
                        JobExtraction.prompt_version.in_(accepted_prompt_versions),
                        JobExtraction.status == "succeeded",
                    ),
                ),
            )
            .exists()
        )
        extracted_before = (
            select(JobExtraction.job_extraction_id)
            .where(
                JobExtraction.job_snapshot_id == JobSnapshot.job_snapshot_id,
                JobExtraction.status == "succeeded",
            )
            .exists()
        )
        put_away = (
            select(JobInboxItem.job_inbox_item_id)
            .join(
                JobOpportunityLink,
                JobOpportunityLink.job_opportunity_id == JobInboxItem.job_opportunity_id,
            )
            .where(
                JobOpportunityLink.job_posting_id == JobSnapshot.job_posting_id,
                JobOpportunityLink.state != "rejected",
                JobInboxItem.state.in_([InboxState.IGNORED.value, InboxState.ARCHIVED.value]),
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
                ~and_(
                    extracted_before, or_(put_away, _set_aside(JobSnapshot, below=set_aside_below))
                ),
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
        set_aside_below: int = 0,
    ) -> tuple[JobExtraction, JobSnapshot] | None:
        """Claim the next waiting extraction for this provider and model, with its snapshot.

        A row claimed by a worker that died (claim older than ``stale_before``) is reclaimed.
        Snapshots never extracted come before re-extractions of a newer prompt or taxonomy, so a
        new job is not stuck behind a backlog of jobs that already have an answer (ADR-073). A
        re-extraction of a job the main inbox sets aside is left waiting: it was queued before
        the job was set aside and would only spend model time.
        """
        earlier = aliased(JobExtraction)
        has_earlier_answer = (
            select(earlier.job_extraction_id)
            .where(
                earlier.job_snapshot_id == JobExtraction.job_snapshot_id,
                earlier.status == "succeeded",
            )
            .exists()
        )
        statement = (
            select(JobExtraction, JobSnapshot)
            .join(JobSnapshot, JobSnapshot.job_snapshot_id == JobExtraction.job_snapshot_id)
            .where(
                JobExtraction.status == "pending",
                JobExtraction.provider == provider,
                JobExtraction.model == model,
                JobExtraction.prompt_version == prompt_version,
                (JobExtraction.claimed_at.is_(None)) | (JobExtraction.claimed_at < stale_before),
                ~and_(has_earlier_answer, _set_aside(JobSnapshot, below=set_aside_below)),
            )
            .order_by(has_earlier_answer, JobExtraction.job_extraction_id)
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
