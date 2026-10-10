"""Data access for the stored judgements of career directions (ADR-057)."""

from collections.abc import Collection
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from jobs_radar.db.models import (
    DirectionJudgement,
    JobExtraction,
    JobPosting,
    JobSnapshot,
    ProfileRevision,
)


class DirectionRepository:
    """Reads and writes ``direction_judgement`` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def latest(
        self, job_snapshot_id: int, hashes: Collection[str], prompt_version: str
    ) -> dict[str, DirectionJudgement]:
        """Return the newest judgement of the snapshot for each of ``hashes`` (any model)."""
        if not hashes:
            return {}
        rows = await self._session.execute(
            select(DirectionJudgement)
            .where(
                DirectionJudgement.job_snapshot_id == job_snapshot_id,
                DirectionJudgement.direction_hash.in_(hashes),
                DirectionJudgement.prompt_version == prompt_version,
            )
            .order_by(DirectionJudgement.direction_judgement_id)
        )
        # Ascending ids, so a later judgement (another model) replaces an earlier one.
        return {row.direction_hash: row for row in rows.scalars()}

    async def add(
        self,
        *,
        job_snapshot_id: int,
        direction_hash: str,
        direction_label: str,
        provider: str,
        model: str,
        prompt_version: str,
        level: str,
        job_quote: str | None,
        direction_quote: str | None,
    ) -> bool:
        """Store a judgement; return ``False`` if the same one already exists."""
        statement = (
            insert(DirectionJudgement)
            .values(
                job_snapshot_id=job_snapshot_id,
                direction_hash=direction_hash,
                direction_label=direction_label,
                provider=provider,
                model=model,
                prompt_version=prompt_version,
                level=level,
                job_quote=job_quote,
                direction_quote=direction_quote,
            )
            .on_conflict_do_nothing(constraint="uq_direction_judgement_inputs")
            .returning(DirectionJudgement.direction_judgement_id)
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def pending(
        self, hashes: Collection[str], prompt_version: str, since: datetime, limit: int
    ) -> list[tuple[int, int, int]]:
        """Return ``(posting, snapshot, extraction)`` ids still to judge, newest jobs first.

        Only open postings first seen at or after ``since`` count, with their latest snapshot and
        its latest successful extraction; a job is pending while it lacks a judgement for any of
        ``hashes``.
        """
        if not hashes:
            return []
        newer_snapshot = aliased(JobSnapshot)
        newer_extraction = aliased(JobExtraction)
        judged = (
            select(func.count(func.distinct(DirectionJudgement.direction_hash)))
            .where(
                DirectionJudgement.job_snapshot_id == JobSnapshot.job_snapshot_id,
                DirectionJudgement.direction_hash.in_(hashes),
                DirectionJudgement.prompt_version == prompt_version,
            )
            .scalar_subquery()
        )
        statement = (
            select(
                JobPosting.job_posting_id,
                JobSnapshot.job_snapshot_id,
                JobExtraction.job_extraction_id,
            )
            .select_from(JobPosting)
            .join(JobSnapshot, JobSnapshot.job_posting_id == JobPosting.job_posting_id)
            .join(
                JobExtraction,
                (JobExtraction.job_snapshot_id == JobSnapshot.job_snapshot_id)
                & (JobExtraction.status == "succeeded"),
            )
            .where(
                JobPosting.closed_at.is_(None),
                JobPosting.first_seen_at >= since,
                JobSnapshot.job_snapshot_id
                == select(func.max(newer_snapshot.job_snapshot_id))
                .where(newer_snapshot.job_posting_id == JobPosting.job_posting_id)
                .scalar_subquery(),
                JobExtraction.job_extraction_id
                == select(func.max(newer_extraction.job_extraction_id))
                .where(
                    newer_extraction.job_snapshot_id == JobSnapshot.job_snapshot_id,
                    newer_extraction.status == "succeeded",
                )
                .scalar_subquery(),
                judged < len(set(hashes)),
            )
            .order_by(JobPosting.first_seen_at.desc(), JobPosting.job_posting_id.desc())
            .limit(limit)
        )
        return [
            (int(a), int(b), int(c)) for a, b, c in (await self._session.execute(statement)).all()
        ]

    async def first_enabled_at(self, career_profile_id: int) -> datetime | None:
        """Return when the first revision with an enabled direction was saved, if there is one.

        This is the cut-off of the worker: only jobs first seen after it are judged on their own.
        """
        rows = await self._session.execute(
            select(ProfileRevision.created_at, ProfileRevision.facts_json)
            .where(ProfileRevision.career_profile_id == career_profile_id)
            .order_by(ProfileRevision.revision_number)
        )
        for created_at, facts in rows.all():
            if any(item.get("enabled", True) for item in facts.get("directions", [])):
                return created_at  # type: ignore[no-any-return]
        return None
