"""Postings and their immutable snapshots (LLD section 2)."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import InputValidationError
from jobs_radar.db.models import JobPosting, JobSnapshot, SourceConfiguration


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
    ) -> tuple[JobPosting, bool]:
        """Create the posting or refresh the existing one; returns ``(posting, created)``.

        An existing posting keeps its ``first_seen_at``, gets a new ``last_seen_at`` and is
        reopened if it had been marked closed.
        """
        if source.company_id is None:
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
                company_id=source.company_id,
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
            return posting, True
        existing.source_url = source_url
        existing.title = title
        existing.current_content_hash = content_hash
        existing.last_seen_at = seen_at
        existing.closed_at = None
        await self._session.flush()
        return existing, False

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
