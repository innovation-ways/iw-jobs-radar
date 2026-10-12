"""Data access for the stored pre-application drafts (ADR-064)."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import ApplicationDraft, JobSnapshot


class ApplicationDraftRepository:
    """Reads and writes ``application_draft`` rows."""

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

    async def add(
        self,
        *,
        job_snapshot_id: int,
        profile_revision_id: int,
        provider: str,
        model: str,
        prompt_version: str,
        draft_json: dict[str, Any],
        latency_ms: int | None,
    ) -> ApplicationDraft:
        """Store a draft; every request adds a row, nothing is replaced."""
        row = ApplicationDraft(
            job_snapshot_id=job_snapshot_id,
            profile_revision_id=profile_revision_id,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            draft_json=draft_json,
            latency_ms=latency_ms,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for_posting(self, job_posting_id: int) -> list[ApplicationDraft]:
        """Return the drafts of every snapshot of the posting, newest first."""
        rows = await self._session.execute(
            select(ApplicationDraft)
            .join(JobSnapshot, JobSnapshot.job_snapshot_id == ApplicationDraft.job_snapshot_id)
            .where(JobSnapshot.job_posting_id == job_posting_id)
            .order_by(ApplicationDraft.application_draft_id.desc())
        )
        return list(rows.scalars())
