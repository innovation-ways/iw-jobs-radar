"""Assess one job against the owner's career directions from the screen (ADR-057).

Uses the local model chosen for job analysis (ADR-046): a direction text never goes to a remote
provider. Without such a model the owner is told to choose one; a model that is down is a 503 and
nothing is stored.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import DependencyUnavailableError, InputValidationError
from jobs_radar.services.ai_settings import AiSettingsService
from jobs_radar.services.direction_service import (
    AssessSummary,
    DirectionService,
    DirectionUnavailable,
)


class DirectionAssessService:
    """Runs :class:`DirectionService` with the owner's local jobs model. The caller commits."""

    def __init__(self, session: AsyncSession, ai: AiSettingsService, *, max_chars: int) -> None:
        self._session = session
        self._ai = ai
        self._max_chars = max_chars

    async def assess(self, owner_id: int, job_posting_id: int) -> AssessSummary:
        """Judge and score one posting.

        Raises:
            NotFoundError: unknown posting.
            InputValidationError: no local model is chosen for job analysis.
            DependencyUnavailableError: the model could not be reached.
        """
        target = await self._ai.direction_target(owner_id)
        if target is None:
            msg = "Choose a local model for job analysis in AI & privacy to assess a job."
            raise InputValidationError(msg)
        _, provider = target
        service = DirectionService(self._session, provider, max_chars=self._max_chars)
        try:
            return await service.assess(owner_id, job_posting_id)
        except DirectionUnavailable as error:
            msg = "The local model could not be reached, so the job was not assessed."
            raise DependencyUnavailableError(msg) from error
