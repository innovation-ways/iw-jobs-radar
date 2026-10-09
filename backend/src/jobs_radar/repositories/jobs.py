"""Postings and their immutable snapshots (LLD section 2)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import InputValidationError
from jobs_radar.db.models import JobChangeEvent, JobPosting, JobSnapshot, SourceConfiguration


@dataclass(frozen=True)
class UpsertResult:
    """Outcome of :meth:`JobRepository.upsert_posting`."""

    posting: JobPosting
    created: bool
    reopened: bool
    previous_content_hash: str | None


class JobRepository:
    """Data access for job postings and snapshots. Change detection lives in the service layer."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_posting(
        self,
        source: SourceConfiguration,
        *,
        external_job_id: str,
        source_url: str,
        title: str,
        content_hash: str,
        seen_at: datetime,
        company_id: int | None = None,
    ) -> UpsertResult:
        """Create the posting or refresh the existing one.

        An existing posting keeps its ``first_seen_at``, gets a new ``last_seen_at`` and is
        reopened if it had been marked closed. The result also carries the content hash the
        posting had before, so callers can tell whether its content changed.
        """
        # A company board has its own company; a job board names the company of each posting.
        owner_company_id = source.company_id if source.company_id is not None else company_id
        if owner_company_id is None:
            msg = "The source has no company; link it to a company before collecting."
            raise InputValidationError(msg)
        existing = (
            await self._session.execute(
                select(JobPosting)
                .where(
                    JobPosting.source_configuration_id == source.source_configuration_id,
                    JobPosting.external_job_id == external_job_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing is None:
            posting = JobPosting(
                source_configuration_id=source.source_configuration_id,
                company_id=owner_company_id,
                external_job_id=external_job_id,
                source_type=source.source_type,
                source_url=source_url,
                title=title,
                current_content_hash=content_hash,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
            self._session.add(posting)
            await self._session.flush()
            return UpsertResult(posting, created=True, reopened=False, previous_content_hash=None)
        previous_hash = existing.current_content_hash
        reopened = existing.closed_at is not None
        existing.source_url = source_url
        existing.title = title
        existing.current_content_hash = content_hash
        existing.last_seen_at = seen_at
        existing.closed_at = None
        await self._session.flush()
        return UpsertResult(
            existing, created=False, reopened=reopened, previous_content_hash=previous_hash
        )

    async def add_snapshot_if_new(
        self,
        posting: JobPosting,
        *,
        content_hash: str,
        fetched_at: datetime,
        raw_payload: Any,
        normalised: Any,
    ) -> tuple[JobSnapshot, bool]:
        """Store a snapshot unless its content hash exists; returns ``(snapshot, created)``."""
        statement = (
            insert(JobSnapshot)
            .values(
                job_posting_id=posting.job_posting_id,
                content_hash=content_hash,
                fetched_at=fetched_at,
                raw_payload_json=raw_payload,
                normalised_json=normalised,
            )
            .on_conflict_do_nothing(index_elements=["job_posting_id", "content_hash"])
            .returning(JobSnapshot.job_snapshot_id)
        )
        inserted_id = (await self._session.execute(statement)).scalar_one_or_none()
        if inserted_id is not None:
            snapshot = await self._session.get(JobSnapshot, inserted_id)
            if snapshot is None:  # cannot happen: the row was inserted in this transaction
                msg = "Snapshot vanished after insert."
                raise RuntimeError(msg)
            return snapshot, True
        existing = (
            await self._session.execute(
                select(JobSnapshot).where(
                    JobSnapshot.job_posting_id == posting.job_posting_id,
                    JobSnapshot.content_hash == content_hash,
                )
            )
        ).scalar_one()
        return existing, False

    async def latest_snapshot(self, job_posting_id: int) -> JobSnapshot | None:
        """Return the most recently fetched snapshot of a posting, if any."""
        result = await self._session.execute(
            select(JobSnapshot)
            .where(JobSnapshot.job_posting_id == job_posting_id)
            .order_by(JobSnapshot.fetched_at.desc(), JobSnapshot.job_snapshot_id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_posting(
        self, source_configuration_id: int, external_job_id: str
    ) -> JobPosting | None:
        """Return the posting with this identity on a source, if it exists."""
        return (
            await self._session.execute(
                select(JobPosting).where(
                    JobPosting.source_configuration_id == source_configuration_id,
                    JobPosting.external_job_id == external_job_id,
                )
            )
        ).scalar_one_or_none()

    async def add_change_event(
        self,
        posting: JobPosting,
        *,
        from_snapshot: JobSnapshot | None,
        to_snapshot: JobSnapshot,
        changed_fields: list[str],
    ) -> JobChangeEvent:
        """Record which material fields changed between two snapshots."""
        event = JobChangeEvent(
            job_posting_id=posting.job_posting_id,
            from_job_snapshot_id=from_snapshot.job_snapshot_id if from_snapshot else None,
            to_job_snapshot_id=to_snapshot.job_snapshot_id,
            changed_fields=changed_fields,
            is_material=True,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def touch_open_postings(self, source_configuration_id: int, seen_at: datetime) -> int:
        """Mark every open posting of a source as seen now (the source said nothing changed)."""
        result = await self._session.execute(
            update(JobPosting)
            .where(
                JobPosting.source_configuration_id == source_configuration_id,
                JobPosting.closed_at.is_(None),
            )
            .values(last_seen_at=seen_at)
            .execution_options(synchronize_session="fetch")
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def close_unseen(
        self,
        source_configuration_id: int,
        seen_ids: set[str],
        *,
        previous_success_started_at: datetime | None,
        closed_at: datetime,
    ) -> int:
        """Close open postings missing from this run that were already missing from the last one.

        A posting is closed only after two consecutive successful runs without it: it must be
        absent now *and* not have been seen since the previous successful run began. With no
        previous successful run nothing is closed.
        """
        if previous_success_started_at is None:
            return 0
        result = await self._session.execute(
            update(JobPosting)
            .where(
                JobPosting.source_configuration_id == source_configuration_id,
                JobPosting.closed_at.is_(None),
                JobPosting.external_job_id.not_in(seen_ids),
                JobPosting.last_seen_at < previous_success_started_at,
            )
            .values(closed_at=closed_at)
            .execution_options(synchronize_session="fetch")
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def open_count(self, source_configuration_ids: list[int]) -> dict[int, int]:
        """Return the number of open postings per source."""
        rows = await self._session.execute(
            select(JobPosting.source_configuration_id, func.count())
            .where(
                JobPosting.source_configuration_id.in_(source_configuration_ids),
                JobPosting.closed_at.is_(None),
            )
            .group_by(JobPosting.source_configuration_id)
        )
        return {int(source_id): int(total) for source_id, total in rows.all()}
