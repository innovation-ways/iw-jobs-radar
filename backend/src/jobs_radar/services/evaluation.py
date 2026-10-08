"""Scoring jobs with ``matching-v1`` and keeping the evaluations (T4.6, document 13, section 8).

Evaluations are append-only: scoring the same snapshot, extraction and revisions again returns the
stored result, and a changed intent or profile creates a *new* evaluation, so history is never
rewritten. The score is a pure function of stored data; the model is used only to judge skill
pairs that have never been judged, and re-scoring after a weight change needs no model at all.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.providers.base import ExtractionProvider
from jobs_radar.core.errors import ConflictError, NotFoundError
from jobs_radar.db.models import (
    CareerProfile,
    Company,
    IntentRevision,
    JobExtraction,
    JobPosting,
    JobSnapshot,
    MatchEvaluation,
    ProfileRevision,
    ScoreDimension,
    SearchIntent,
)
from jobs_radar.domain.enums import EXTRACTION_PROMPT_VERSION
from jobs_radar.domain.matching.engine import POLICY_VERSION, evaluate
from jobs_radar.repositories.evaluations import EvaluationRepository
from jobs_radar.repositories.skills import SkillRepository
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.profile import ProfileFacts
from jobs_radar.services.evaluation_inputs import intent_view, job_attributes, profile_view
from jobs_radar.services.locations import resolve_all
from jobs_radar.services.skills import SkillRelationJudge


def _place_names(attributes: dict[str, Any], snapshot: JobSnapshot) -> list[str]:
    """Return the places to resolve: the extracted ones if known, else the source's own."""
    locations = attributes["output"].get("locations", {})
    if locations.get("status") == "known" and locations.get("value"):
        return [str(place) for place in locations["value"]]
    work = snapshot.normalised_json.get("work_arrangement", {})
    return [loc["raw"] for loc in work.get("locations", []) if loc.get("raw")]


@dataclass(frozen=True)
class EvaluationRecord:
    """A stored evaluation with its dimensions."""

    evaluation: MatchEvaluation
    dimensions: list[ScoreDimension]
    created: bool = False


@dataclass(frozen=True)
class RescoreSummary:
    """How many existing jobs were scored again and how many already had a current score."""

    evaluated: int
    skipped: int


class EvaluationService:
    """Evaluates jobs. The caller owns the transaction."""

    def __init__(self, session: AsyncSession, provider: ExtractionProvider | None) -> None:
        self._session = session
        self._provider = provider
        self._evaluations = EvaluationRepository(session)
        self._skills = SkillRepository(session)

    async def _relations(
        self, job_skill_ids: list[int], profile_skills: set[int], *, judge: bool
    ) -> dict[tuple[int, int], str]:
        """Skill relations the engine may use: cached ones, plus new judgements when allowed."""
        relations: dict[tuple[int, int], str] = {}
        judge_pairs = judge and self._provider is not None
        for skill_id in job_skill_ids:
            if skill_id in profile_skills:
                continue  # held by the profile: no relation needed
            if judge_pairs and self._provider is not None:
                found = await SkillRelationJudge(self._session, self._provider).relations(
                    skill_id, sorted(profile_skills)
                )
            else:
                found = await self._skills.cached_relations(skill_id, sorted(profile_skills))
            relations.update({(skill_id, other): relation for other, relation in found.items()})
        return relations

    async def _owned_revisions(
        self, owner_id: int, profile_revision_id: int, intent_revision_id: int
    ) -> tuple[ProfileRevision, IntentRevision]:
        profile = (
            await self._session.execute(
                select(ProfileRevision)
                .join(
                    CareerProfile,
                    CareerProfile.career_profile_id == ProfileRevision.career_profile_id,
                )
                .where(
                    ProfileRevision.profile_revision_id == profile_revision_id,
                    CareerProfile.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        intent = (
            await self._session.execute(
                select(IntentRevision)
                .join(
                    SearchIntent, SearchIntent.search_intent_id == IntentRevision.search_intent_id
                )
                .where(
                    IntentRevision.intent_revision_id == intent_revision_id,
                    SearchIntent.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if profile is None or intent is None:
            msg = "Profile or intent revision not found."
            raise NotFoundError(msg)
        return profile, intent

    async def evaluate(
        self,
        owner_id: int,
        *,
        job_snapshot_id: int,
        job_extraction_id: int,
        profile_revision_id: int,
        intent_revision_id: int,
        judge: bool,
    ) -> EvaluationRecord:
        """Score one extracted snapshot under exact profile and intent revisions.

        Args:
            judge: allow the model to judge skill pairs that were never judged. Without it (or
                without a provider) only cached judgements are used.

        Raises:
            NotFoundError: unknown snapshot, or a revision that is not the owner's.
            ConflictError: the extraction did not succeed (the job is "not evaluated").
        """
        profile_revision, intent_revision = await self._owned_revisions(
            owner_id, profile_revision_id, intent_revision_id
        )
        extraction = await self._session.get(JobExtraction, job_extraction_id)
        snapshot = await self._session.get(JobSnapshot, job_snapshot_id)
        if extraction is None or snapshot is None or extraction.job_snapshot_id != job_snapshot_id:
            msg = "Job snapshot or extraction not found."
            raise NotFoundError(msg)
        if extraction.status != "succeeded" or extraction.attributes_json is None:
            msg = "The job has not been extracted yet, so it cannot be evaluated."
            raise ConflictError(msg)
        posting = await self._session.get(JobPosting, snapshot.job_posting_id)
        company = await self._session.get(Company, posting.company_id) if posting else None

        # Places are resolved here (offline and cheap) rather than trusted from the stored result:
        # the board's own locations are the reliable source, and gazetteer improvements then apply
        # to extractions that were stored earlier.
        attributes = dict(extraction.attributes_json)
        attributes["locations_resolved"] = resolve_all(_place_names(attributes, snapshot))
        job = job_attributes(
            attributes,
            snapshot.normalised_json["title"],
            snapshot.normalised_json["description_text"],
            company.canonical_name if company else "",
        )
        profile = profile_view(ProfileFacts.model_validate(profile_revision.facts_json))
        definition = IntentDefinition.model_validate(intent_revision.intent_json)
        relations = await self._relations(
            [skill.skill_id for skill in job.skills], set(profile.skill_levels), judge=judge
        )
        result = evaluate(job, profile, intent_view(definition), relations)

        evaluation, dimensions, created = await self._evaluations.add(
            job_snapshot_id=job_snapshot_id,
            job_extraction_id=job_extraction_id,
            profile_revision_id=profile_revision_id,
            intent_revision_id=intent_revision_id,
            policy_version=POLICY_VERSION,
            job_source_hash=snapshot.content_hash,
            fit_score=result.fit_score,
            recommendation=result.recommendation,
            gates=[
                {"code": g.code, "reason": g.reason, "evidence": dict(g.evidence)}
                for g in result.gates
            ],
            weights=definition.weights.model_dump(),
            dimensions=[
                {
                    "dimension_key": d.key,
                    "status": d.status,
                    "quality": d.quality,
                    "weight": d.weight,
                    "effective_weight": d.effective_weight,
                    "strength": d.strength if d.strength is not None else 0,
                    "contribution": d.contribution,
                    "excluded": d.excluded,
                    "evidence_json": dict(d.evidence),
                    "explanation": d.explanation,
                }
                for d in result.dimensions
            ],
        )
        return EvaluationRecord(evaluation, dimensions, created)

    async def evaluate_posting(
        self,
        owner_id: int,
        job_posting_id: int,
        *,
        profile_revision_id: int,
        intent_revision_id: int,
    ) -> EvaluationRecord:
        """Score a posting's latest snapshot with its latest successful extraction (no model call).

        Raises:
            NotFoundError: unknown posting, or a revision that is not the owner's.
            ConflictError: the posting has no successful extraction yet.
        """
        posting = await self._session.get(JobPosting, job_posting_id)
        if posting is None:
            msg = "Job posting not found."
            raise NotFoundError(msg)
        found = await self._evaluations.latest_extraction(job_posting_id)
        if found is None:
            msg = "The job has not been extracted yet, so it cannot be evaluated."
            raise ConflictError(msg)
        snapshot_id, extraction_id = found
        return await self.evaluate(
            owner_id,
            job_snapshot_id=snapshot_id,
            job_extraction_id=extraction_id,
            profile_revision_id=profile_revision_id,
            intent_revision_id=intent_revision_id,
            judge=False,
        )

    async def evaluate_pending(
        self,
        *,
        intent_id: int | None = None,
        limit: int = 200,
        extraction_filter: tuple[str, str, str] | None = None,
    ) -> int:
        """Score jobs that were never scored for an enabled intent; return how many were scored.

        Existing scores are left alone: new weights apply from now on (re-scoring is explicit).
        """
        pending = await self._evaluations.pending(
            mode="new",
            policy_version=POLICY_VERSION,
            intent_id=intent_id,
            limit=limit,
            extraction_filter=extraction_filter,
        )
        for item in pending:
            await self.evaluate(
                item.owner_id,
                job_snapshot_id=item.job_snapshot_id,
                job_extraction_id=item.job_extraction_id,
                profile_revision_id=item.profile_revision_id,
                intent_revision_id=item.intent_revision_id,
                judge=True,
            )
        return len(pending)

    async def rescore(self, owner_id: int, intent_id: int, *, limit: int = 1000) -> RescoreSummary:
        """Score existing jobs again under the intent's current revisions, using no model.

        Raises:
            NotFoundError: unknown or foreign intent.
        """
        intent = (
            await self._session.execute(
                select(SearchIntent).where(
                    SearchIntent.search_intent_id == intent_id, SearchIntent.owner_id == owner_id
                )
            )
        ).scalar_one_or_none()
        if intent is None:
            msg = "Search intent not found."
            raise NotFoundError(msg)
        pending = await self._evaluations.pending(
            mode="rescore", policy_version=POLICY_VERSION, intent_id=intent_id, limit=limit
        )
        for item in pending:
            await self.evaluate(
                owner_id,
                job_snapshot_id=item.job_snapshot_id,
                job_extraction_id=item.job_extraction_id,
                profile_revision_id=item.profile_revision_id,
                intent_revision_id=item.intent_revision_id,
                judge=False,
            )
        total = await self._evaluations.count_scored(intent_id, POLICY_VERSION)
        return RescoreSummary(evaluated=len(pending), skipped=max(0, total - len(pending)))

    async def get(self, owner_id: int, match_evaluation_id: int) -> EvaluationRecord:
        """Return one stored evaluation with its dimensions."""
        evaluation, dimensions = await self._evaluations.get(owner_id, match_evaluation_id)
        return EvaluationRecord(evaluation, dimensions)


class EvaluationRunner:
    """Scores new jobs for every enabled intent in its own transaction (used by the worker)."""

    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        provider: ExtractionProvider,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider

    async def run(self, limit: int = 200) -> int:
        """Score jobs extracted by the current model that were never scored; return how many."""
        async with self._session_factory() as session:
            scored = await EvaluationService(session, self._provider).evaluate_pending(
                limit=limit,
                extraction_filter=(
                    self._provider.provider,
                    self._provider.model,
                    EXTRACTION_PROMPT_VERSION,
                ),
            )
            await session.commit()
            return scored
