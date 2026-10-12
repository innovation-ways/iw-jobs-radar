"""Write and list the pre-application drafts of one job from the screen (ADR-064).

Uses the local model chosen for job analysis (ADR-046), in its larger variant when the owner set
one for directions: the profile facts and the job text never go to a remote provider. Without such
a model the owner is told to choose one; a model that is down, or an answer that stays unusable,
is a 503 for this call and nothing is stored.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import (
    DependencyUnavailableError,
    InputValidationError,
    NotFoundError,
)
from jobs_radar.db.models import ApplicationDraft, Company, JobPosting, JobSnapshot
from jobs_radar.domain.enums import APPLICATION_PROMPT_VERSION, LOCAL_OWNER_ID
from jobs_radar.repositories.application_drafts import ApplicationDraftRepository
from jobs_radar.repositories.revisions import IntentRepository
from jobs_radar.schemas.profile import ProfileFacts
from jobs_radar.services.ai_settings import AiSettingsService
from jobs_radar.services.application_profile import describe_profile
from jobs_radar.services.application_writer import (
    INFRASTRUCTURE,
    ApplicationError,
    ApplicationWriter,
)
from jobs_radar.services.profiles import ProfileService, RevisionView

logger = structlog.get_logger()


class ApplicationDraftService:
    """Writes and reads drafts with the owner's local jobs model. The caller commits."""

    def __init__(self, session: AsyncSession, ai: AiSettingsService, *, max_chars: int) -> None:
        self._session = session
        self._ai = ai
        self._max_chars = max_chars
        self._repo = ApplicationDraftRepository(session)

    async def _profile_revision(self, owner_id: int) -> RevisionView:
        """Return the current revision of the profile that scores the jobs.

        That is the first enabled intent's profile, else the owner's first profile that has a
        revision.
        """
        views = await ProfileService(self._session).list_profiles(owner_id)
        with_revision = [v for v in views if v.current is not None]
        if not with_revision:
            msg = "Save your Career Profile first: the draft is written from its facts."
            raise InputValidationError(msg)
        for intent in await IntentRepository(self._session).list_enabled(owner_id):
            for view in with_revision:
                if view.profile.career_profile_id == intent.career_profile_id:
                    assert view.current is not None  # noqa: S101  # filtered above
                    return view.current
        first = with_revision[0].current
        assert first is not None  # noqa: S101  # filtered above
        return first

    async def generate(
        self, job_posting_id: int, *, owner_id: int = LOCAL_OWNER_ID
    ) -> ApplicationDraft:
        """Write and store a new draft for the posting's latest snapshot.

        Raises:
            NotFoundError: unknown posting.
            InputValidationError: no local model is chosen, or the owner has no saved profile.
            DependencyUnavailableError: the model could not be reached or gave no usable draft.
        """
        snapshot_id = await self._repo.latest_snapshot_id(job_posting_id)
        if snapshot_id is None:
            msg = "Job posting not found."
            raise NotFoundError(msg)
        target = await self._ai.direction_target(owner_id)
        if target is None:
            msg = "Choose a local model for job analysis in AI & privacy to write a draft."
            raise InputValidationError(msg)
        _, provider = target
        revision = await self._profile_revision(owner_id)
        facts = ProfileFacts.model_validate(revision.revision.facts_json)
        digest = describe_profile(facts, revision.skill_names)
        posting = await self._session.get(JobPosting, job_posting_id)
        snapshot = await self._session.get(JobSnapshot, snapshot_id)
        assert posting is not None and snapshot is not None  # noqa: S101  # ids come from queries
        company = await self._session.get(Company, posting.company_id)
        normalised = snapshot.normalised_json
        try:
            outcome = await ApplicationWriter(provider, max_chars=self._max_chars).write(
                company=company.canonical_name if company else "",
                title=normalised["title"],
                description=normalised["description_text"],
                digest=digest,
            )
        except ApplicationError as error:
            # The reason (field paths and rules only, no text) is what tells a prompt problem from
            # a model that is down.
            logger.warning(
                "application_draft_failed",
                error_class=error.error_class,
                reason=str(error.__cause__ or error.message)[:400],
            )
            if error.error_class in {c.value for c in INFRASTRUCTURE}:
                msg = "The local model could not be reached, so the draft was not written."
                raise DependencyUnavailableError(msg) from error
            msg = "The model's answer could not be used as a draft. Try again."
            raise DependencyUnavailableError(msg) from error
        return await self._repo.add(
            job_snapshot_id=snapshot_id,
            profile_revision_id=revision.revision.profile_revision_id,
            provider=provider.provider,
            model=provider.model,
            prompt_version=APPLICATION_PROMPT_VERSION,
            draft_json=outcome.draft.model_dump(mode="json"),
            latency_ms=outcome.latency_ms,
        )

    async def list_drafts(self, job_posting_id: int) -> list[ApplicationDraft]:
        """Return the drafts of the posting, newest first.

        Raises:
            NotFoundError: unknown posting.
        """
        if await self._session.get(JobPosting, job_posting_id) is None:
            msg = "Job posting not found."
            raise NotFoundError(msg)
        return await self._repo.list_for_posting(job_posting_id)
