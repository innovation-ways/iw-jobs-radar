"""Data access for evaluations and the work queue of jobs still to be scored (LLD section 2)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import (
    CareerProfile,
    IntentRevision,
    JobExtraction,
    JobPosting,
    JobSnapshot,
    MatchEvaluation,
    ScoreDimension,
    SearchIntent,
)


@dataclass(frozen=True)
class PendingEvaluation:
    """One job that still needs a score under the current revisions of an intent."""

    owner_id: int
    search_intent_id: int
    job_snapshot_id: int
    job_extraction_id: int
    profile_revision_id: int
    intent_revision_id: int


class EvaluationRepository:
    """Reads and writes ``match_evaluation`` and ``score_dimension`` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        job_snapshot_id: int,
        job_extraction_id: int,
        profile_revision_id: int,
        intent_revision_id: int,
        policy_version: str,
        job_source_hash: str,
        fit_score: int,
        recommendation: str,
        gates: list[dict[str, Any]],
        weights: dict[str, int],
        dimensions: Sequence[dict[str, Any]],
    ) -> tuple[MatchEvaluation, list[ScoreDimension], bool]:
        """Store an evaluation and its dimensions, or return the one that already exists.

        The inputs are unique, so scoring the same snapshot, extraction and revisions twice
        returns the first result (evaluations are immutable). The last item says if it is new.
        """
        statement = (
            insert(MatchEvaluation)
            .values(
                job_snapshot_id=job_snapshot_id,
                job_extraction_id=job_extraction_id,
                profile_revision_id=profile_revision_id,
                intent_revision_id=intent_revision_id,
                policy_version=policy_version,
                job_source_hash=job_source_hash,
                fit_score=fit_score,
                recommendation=recommendation,
                gates_json=gates,
                weights_json=weights,
            )
            .on_conflict_do_nothing(constraint="uq_match_evaluation_inputs")
            .returning(MatchEvaluation.match_evaluation_id)
        )
        new_id = (await self._session.execute(statement)).scalar_one_or_none()
        if new_id is None:
            existing = (
                await self._session.execute(
                    select(MatchEvaluation).where(
                        MatchEvaluation.job_snapshot_id == job_snapshot_id,
                        MatchEvaluation.job_extraction_id == job_extraction_id,
                        MatchEvaluation.profile_revision_id == profile_revision_id,
                        MatchEvaluation.intent_revision_id == intent_revision_id,
                        MatchEvaluation.policy_version == policy_version,
                    )
                )
            ).scalar_one()
            return existing, await self.dimensions(existing.match_evaluation_id), False
        evaluation = await self._session.get(MatchEvaluation, new_id)
        assert evaluation is not None  # noqa: S101  # inserted in this transaction
        rows = [ScoreDimension(match_evaluation_id=new_id, **dimension) for dimension in dimensions]
        self._session.add_all(rows)
        await self._session.flush()
        return evaluation, rows, True

    async def latest_extraction(self, job_posting_id: int) -> tuple[int, int] | None:
        """Return ``(snapshot id, extraction id)`` for the latest snapshot, if it was extracted."""
        snapshot_id = (
            await self._session.execute(
                select(func.max(JobSnapshot.job_snapshot_id)).where(
                    JobSnapshot.job_posting_id == job_posting_id
                )
            )
        ).scalar_one_or_none()
        if snapshot_id is None:
            return None
        extraction_id = (
            await self._session.execute(
                select(func.max(JobExtraction.job_extraction_id)).where(
                    JobExtraction.job_snapshot_id == snapshot_id,
                    JobExtraction.status == "succeeded",
                )
            )
        ).scalar_one_or_none()
        return None if extraction_id is None else (int(snapshot_id), int(extraction_id))

    async def dimensions(self, match_evaluation_id: int) -> list[ScoreDimension]:
        """Return the dimensions of an evaluation in a stable order."""
        rows = await self._session.execute(
            select(ScoreDimension)
            .where(ScoreDimension.match_evaluation_id == match_evaluation_id)
            .order_by(ScoreDimension.score_dimension_id)
        )
        return list(rows.scalars())

    async def get(
        self, owner_id: int, match_evaluation_id: int
    ) -> tuple[MatchEvaluation, list[ScoreDimension]]:
        """Return the owner's evaluation; ``NotFoundError`` for unknown or foreign ids."""
        evaluation = (
            await self._session.execute(
                select(MatchEvaluation)
                .join(
                    IntentRevision,
                    IntentRevision.intent_revision_id == MatchEvaluation.intent_revision_id,
                )
                .join(
                    SearchIntent, SearchIntent.search_intent_id == IntentRevision.search_intent_id
                )
                .where(
                    MatchEvaluation.match_evaluation_id == match_evaluation_id,
                    SearchIntent.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if evaluation is None:
            msg = "Evaluation not found."
            raise NotFoundError(msg)
        return evaluation, await self.dimensions(match_evaluation_id)

    # --- work queue ----------------------------------------------------------------------------

    def _candidates(
        self,
        *,
        policy_version: str,
        intent_id: int | None,
        extraction_filter: tuple[str, str, str] | None,
    ) -> Any:
        """Latest snapshot of each open posting with its latest successful extraction."""
        newer_snapshot = aliased(JobSnapshot)
        newer_extraction = aliased(JobExtraction)
        extraction_conditions = [JobExtraction.status == "succeeded"]
        newer_conditions = [
            newer_extraction.job_snapshot_id == JobExtraction.job_snapshot_id,
            newer_extraction.status == "succeeded",
        ]
        if extraction_filter is not None:
            provider, model, prompt = extraction_filter
            extraction_conditions += [
                JobExtraction.provider == provider,
                JobExtraction.model == model,
                JobExtraction.prompt_version == prompt,
            ]
            newer_conditions += [
                newer_extraction.provider == provider,
                newer_extraction.model == model,
                newer_extraction.prompt_version == prompt,
            ]
        statement = (
            select(
                SearchIntent.owner_id,
                SearchIntent.search_intent_id,
                JobExtraction.job_snapshot_id,
                JobExtraction.job_extraction_id,
                CareerProfile.current_profile_revision_id,
                SearchIntent.current_intent_revision_id,
            )
            .select_from(SearchIntent)
            .join(CareerProfile, CareerProfile.career_profile_id == SearchIntent.career_profile_id)
            .join(JobExtraction, and_(*extraction_conditions))
            .join(JobSnapshot, JobSnapshot.job_snapshot_id == JobExtraction.job_snapshot_id)
            .join(JobPosting, JobPosting.job_posting_id == JobSnapshot.job_posting_id)
            .where(
                SearchIntent.enabled.is_(True),
                SearchIntent.current_intent_revision_id.is_not(None),
                CareerProfile.current_profile_revision_id.is_not(None),
                JobPosting.closed_at.is_(None),
                JobSnapshot.job_snapshot_id
                == select(func.max(newer_snapshot.job_snapshot_id))
                .where(newer_snapshot.job_posting_id == JobSnapshot.job_posting_id)
                .scalar_subquery(),
                JobExtraction.job_extraction_id
                == select(func.max(newer_extraction.job_extraction_id))
                .where(*newer_conditions)
                .scalar_subquery(),
            )
            .order_by(JobPosting.first_seen_at.desc(), JobExtraction.job_extraction_id.desc())
        )
        if intent_id is not None:
            statement = statement.where(SearchIntent.search_intent_id == intent_id)
        del policy_version  # applied by the callers' exists() clauses
        return statement

    def _scored_for_intent(self, policy_version: str) -> Any:
        """Whether the snapshot has any evaluation for the intent (under any revision)."""
        evaluation = aliased(MatchEvaluation)
        revision = aliased(IntentRevision)
        return (
            select(evaluation.match_evaluation_id)
            .join(revision, revision.intent_revision_id == evaluation.intent_revision_id)
            .where(
                evaluation.job_snapshot_id == JobExtraction.job_snapshot_id,
                revision.search_intent_id == SearchIntent.search_intent_id,
                evaluation.policy_version == policy_version,
            )
            .exists()
        )

    def _scored_exactly(self, policy_version: str) -> Any:
        """Whether this snapshot, extraction and the current revisions already have a score."""
        evaluation = aliased(MatchEvaluation)
        return (
            select(evaluation.match_evaluation_id)
            .where(
                evaluation.job_snapshot_id == JobExtraction.job_snapshot_id,
                evaluation.job_extraction_id == JobExtraction.job_extraction_id,
                evaluation.profile_revision_id == CareerProfile.current_profile_revision_id,
                evaluation.intent_revision_id == SearchIntent.current_intent_revision_id,
                evaluation.policy_version == policy_version,
            )
            .exists()
        )

    async def pending(
        self,
        *,
        mode: str,
        policy_version: str,
        intent_id: int | None,
        limit: int,
        extraction_filter: tuple[str, str, str] | None = None,
    ) -> list[PendingEvaluation]:
        """Return the jobs to score.

        ``new``: never scored for the intent. ``rescore``: scored before, but not yet under the
        current revisions of the intent and its profile.
        """
        statement = self._candidates(
            policy_version=policy_version, intent_id=intent_id, extraction_filter=extraction_filter
        )
        if mode == "new":
            statement = statement.where(~self._scored_for_intent(policy_version))
        else:
            statement = statement.where(
                self._scored_for_intent(policy_version), ~self._scored_exactly(policy_version)
            )
        rows = (await self._session.execute(statement.limit(limit))).all()
        return [
            PendingEvaluation(
                owner_id=int(owner_id),
                search_intent_id=int(intent),
                job_snapshot_id=int(snapshot),
                job_extraction_id=int(extraction),
                profile_revision_id=int(profile_revision),
                intent_revision_id=int(intent_revision),
            )
            for owner_id, intent, snapshot, extraction, profile_revision, intent_revision in rows
        ]

    async def queue_counts(
        self,
        intent_id: int,
        policy_version: str,
        extraction_filter: tuple[str, str, str] | None,
    ) -> tuple[int, int]:
        """Return ``(analysed jobs, of which scored)`` for the intent, as the worker sees them."""
        statement = self._candidates(
            policy_version=policy_version,
            intent_id=intent_id,
            extraction_filter=extraction_filter,
        )
        eligible = (
            await self._session.execute(select(func.count()).select_from(statement.subquery()))
        ).scalar_one()
        scored_statement = statement.where(self._scored_for_intent(policy_version))
        scored = (
            await self._session.execute(
                select(func.count()).select_from(scored_statement.subquery())
            )
        ).scalar_one()
        return int(eligible), int(scored)

    async def count_scored(self, intent_id: int, policy_version: str) -> int:
        """Count open postings whose latest snapshot has been scored for the intent."""
        statement = self._candidates(
            policy_version=policy_version, intent_id=intent_id, extraction_filter=None
        ).where(self._scored_for_intent(policy_version))
        return len((await self._session.execute(statement)).all())
