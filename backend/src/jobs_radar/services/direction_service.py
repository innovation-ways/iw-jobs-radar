"""Judges jobs against the owner's career directions and scores them again (ADR-057).

Two entry points share the same steps: ``assess`` (one posting, on demand, whenever it was first
seen) and ``run_pending`` (the worker: only jobs first seen after the first direction was saved,
so the past is never judged in bulk). For each enabled direction without a judgement the local
model is asked once; the judgement is stored, then the job gets a new evaluation under every
enabled intent, because the stored judgements are part of what a score is based on. A model that
is down raises :class:`DirectionUnavailable` and stores nothing, so the job simply waits.
"""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.providers.base import ExtractionProvider
from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import (
    CareerProfile,
    JobPosting,
    JobSnapshot,
    ProfileRevision,
    SearchIntent,
)
from jobs_radar.domain.directions import direction_hash
from jobs_radar.domain.enums import DIRECTION_PROMPT_VERSION, LOCAL_OWNER_ID
from jobs_radar.repositories.directions import DirectionRepository
from jobs_radar.repositories.evaluations import EvaluationRepository
from jobs_radar.repositories.revisions import IntentRepository
from jobs_radar.schemas.profile import ProfileFacts
from jobs_radar.services.direction_judge import DirectionError, DirectionJudge, DirectionTarget
from jobs_radar.services.evaluation import EvaluationService

logger = structlog.get_logger()


class DirectionUnavailable(Exception):  # noqa: N818  # a condition, like ExtractionError's infrastructure case
    """The model could not be reached or lacks its model; nothing was stored."""


@dataclass(frozen=True)
class AssessSummary:
    """How many judgements were made and how many new evaluations were stored."""

    judged: int
    evaluated: int


@dataclass(frozen=True)
class _Context:
    """One enabled intent with the profile revision whose directions apply."""

    intent: SearchIntent
    profile: CareerProfile
    profile_revision: ProfileRevision
    targets: dict[str, DirectionTarget]


class DirectionService:
    """Judges and scores. The caller owns the transaction."""

    def __init__(
        self, session: AsyncSession, provider: ExtractionProvider, *, max_chars: int
    ) -> None:
        self._session = session
        self._provider = provider
        self._judge = DirectionJudge(provider, max_chars=max_chars)
        self._repo = DirectionRepository(session)
        self._evaluations = EvaluationRepository(session)
        self._evaluator = EvaluationService(session, provider=None)

    async def contexts(self, owner_id: int) -> list[_Context]:
        """Return the enabled intents whose profile has at least one enabled direction."""
        contexts: list[_Context] = []
        for intent in await IntentRepository(self._session).list_enabled(owner_id):
            profile = await self._session.get(CareerProfile, intent.career_profile_id)
            if (
                profile is None
                or profile.current_profile_revision_id is None
                or intent.current_intent_revision_id is None
            ):
                continue
            revision = await self._session.get(ProfileRevision, profile.current_profile_revision_id)
            if revision is None:
                continue
            facts = ProfileFacts.model_validate(revision.facts_json)
            targets = {
                direction_hash(d.text): DirectionTarget(d.label, d.text)
                for d in facts.directions
                if d.enabled
            }
            if targets:
                contexts.append(_Context(intent, profile, revision, targets))
        return contexts

    async def _judge_missing(
        self,
        contexts: list[_Context],
        snapshot_id: int,
        title: str,
        description: str,
        *,
        rejudge: bool = False,
    ) -> int:
        """Judge every enabled direction that has no judgement for the snapshot.

        With ``rejudge`` every direction is judged again by this provider (a new row, so the
        newest judgement counts); it is used to compare models on a sample.
        """
        wanted = {h: t for context in contexts for h, t in context.targets.items()}
        have = await self._repo.latest(snapshot_id, wanted.keys(), DIRECTION_PROMPT_VERSION)
        judged = 0
        for text_hash, target in wanted.items():
            if text_hash in have and not rejudge:
                continue
            try:
                outcome = await self._judge.judge(target, title=title, description=description)
                level, job_quote, direction_quote = (
                    outcome.level,
                    outcome.job_quote,
                    outcome.direction_quote,
                )
            except DirectionError as error:
                if not error.counts_as_attempt:
                    raise DirectionUnavailable(error.message) from error
                if error.error_class != "invalid_output":
                    continue  # a timeout or similar: tried again later
                # An answer that stays unusable is a result ("could not tell"), so the job is
                # not asked again and again.
                level, job_quote, direction_quote = "unknown", None, None
            stored = await self._repo.add(
                job_snapshot_id=snapshot_id,
                direction_hash=text_hash,
                direction_label=target.label,
                provider=self._provider.provider,
                model=self._provider.model,
                prompt_version=DIRECTION_PROMPT_VERSION,
                level=level,
                job_quote=job_quote,
                direction_quote=direction_quote,
            )
            judged += int(stored)
        return judged

    async def _assess_snapshot(
        self,
        owner_id: int,
        contexts: list[_Context],
        snapshot_id: int,
        extraction_id: int,
        *,
        rejudge: bool = False,
    ) -> AssessSummary:

        snapshot = await self._session.get(JobSnapshot, snapshot_id)
        assert snapshot is not None  # noqa: S101  # the id comes from a query in this transaction
        normalised = snapshot.normalised_json
        judged = await self._judge_missing(
            contexts,
            snapshot_id,
            normalised["title"],
            normalised["description_text"],
            rejudge=rejudge,
        )
        evaluated = 0
        for context in contexts:
            record = await self._evaluator.evaluate(
                owner_id,
                job_snapshot_id=snapshot_id,
                job_extraction_id=extraction_id,
                profile_revision_id=context.profile_revision.profile_revision_id,
                intent_revision_id=context.intent.current_intent_revision_id,  # type: ignore[arg-type]
                judge=False,
            )
            evaluated += int(record.created)
        return AssessSummary(judged, evaluated)

    async def assess(
        self, owner_id: int, job_posting_id: int, *, rejudge: bool = False
    ) -> AssessSummary:
        """Judge one posting against every enabled direction and score it again.

        ``rejudge`` asks the model again even if the direction was judged before.

        Raises:
            NotFoundError: unknown posting.
            DirectionUnavailable: the model could not be reached.
        """
        if await self._session.get(JobPosting, job_posting_id) is None:
            msg = "Job posting not found."
            raise NotFoundError(msg)
        contexts = await self.contexts(owner_id)
        found = await self._evaluations.latest_extraction(job_posting_id)
        if not contexts or found is None:
            return AssessSummary(0, 0)
        snapshot_id, extraction_id = found
        return await self._assess_snapshot(
            owner_id, contexts, snapshot_id, extraction_id, rejudge=rejudge
        )

    async def run_pending(self, owner_id: int = LOCAL_OWNER_ID, *, limit: int = 1) -> int:
        """Judge jobs first seen after the first direction was saved; return how many were done."""
        done = 0
        for context in await self.contexts(owner_id):
            since = await self._repo.first_enabled_at(context.profile.career_profile_id)
            if since is None:
                continue
            pending = await self._repo.pending(
                context.targets.keys(), DIRECTION_PROMPT_VERSION, since, limit - done
            )
            for _, snapshot_id, extraction_id in pending:
                await self._assess_snapshot(owner_id, [context], snapshot_id, extraction_id)
                done += 1
            if done >= limit:
                break
        return done


class DirectionRunner:
    """Judges new jobs for the worker, one short transaction per job (ADR-057)."""

    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        provider: ExtractionProvider,
        *,
        max_chars: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._max_chars = max_chars
        self._clock = clock or (lambda: datetime.now(UTC))

    async def run(
        self,
        limit: int = 50,
        *,
        budget_seconds: float = 45.0,
        heartbeat: Callable[[], Awaitable[None]] | None = None,
    ) -> int:
        """Judge pending jobs for a bounded time and return how many were done.

        A model that is down ends the batch quietly: the jobs wait and are never marked as
        failed, and the rest of the worker's iteration carries on.
        """
        deadline = self._clock() + timedelta(seconds=budget_seconds)
        done = 0
        while done < limit and self._clock() < deadline:
            async with self._session_factory() as session:
                service = DirectionService(session, self._provider, max_chars=self._max_chars)
                try:
                    judged = await service.run_pending(limit=1)
                except DirectionUnavailable:
                    logger.warning("directions_model_unavailable")
                    break
                await session.commit()
            if judged == 0:
                break
            done += judged
            if heartbeat is not None:
                await heartbeat()
        return done
