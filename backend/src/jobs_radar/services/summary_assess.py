"""Write the summary of one job from the screen (ADR-059).

Uses the local model chosen for job analysis (ADR-046), in its larger variant when the owner set
one for directions: job text never goes to a remote provider.
Without such a model the owner is told to choose one; a model that is down, or an answer that
stays unusable, is a 503 for this call (an unusable one is also kept as a failed attempt).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import DependencyUnavailableError, InputValidationError
from jobs_radar.services.ai_settings import AiSettingsService
from jobs_radar.services.job_summary import SummaryResult, SummaryService, SummaryUnavailable


class SummaryAssessService:
    """Runs :class:`SummaryService` with the owner's local jobs model. The caller commits."""

    def __init__(self, session: AsyncSession, ai: AiSettingsService, *, max_chars: int) -> None:
        self._session = session
        self._ai = ai
        self._max_chars = max_chars

    async def summarise(self, job_posting_id: int, *, owner_id: int = 1) -> SummaryResult:
        """Return the posting's summary, writing it if it is missing.

        Raises:
            NotFoundError: unknown posting.
            InputValidationError: no local model is chosen for job analysis.
            DependencyUnavailableError: the model could not be reached or gave no usable summary.
        """
        target = await self._ai.direction_target(owner_id)
        if target is None:
            msg = "Choose a local model for job analysis in AI & privacy to write a summary."
            raise InputValidationError(msg)
        _, provider = target
        service = SummaryService(self._session, provider, max_chars=self._max_chars)
        try:
            result = await service.summarise(job_posting_id)
        except SummaryUnavailable as error:
            msg = "The local model could not be reached, so the summary was not written."
            raise DependencyUnavailableError(msg) from error
        if result.text is None:
            msg = (
                "The model's answer could not be used as a summary. Try again or open the original."
            )
            raise DependencyUnavailableError(msg)
        return result
