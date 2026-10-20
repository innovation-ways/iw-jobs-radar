"""Analyse open jobs again with the current prompt, when the owner asks (ADR-080, phase 6c).

A new prompt never re-extracts answered jobs by itself (ADR-077): it costs local-model time and,
for most owners, changes little. This service is the explicit action: it counts the open, recent
jobs that only have an answer from an older, accepted prompt, says how long analysing them would
take at the pace of the latest analyses, and queues them when the owner confirms.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import ConflictError
from jobs_radar.domain.enums import EXTRACTION_ACCEPTED_PROMPT_VERSIONS, EXTRACTION_PROMPT_VERSION
from jobs_radar.repositories.extractions import ExtractionRepository
from jobs_radar.repositories.providers import ProviderRepository
from jobs_radar.repositories.schedule import ScheduleRepository

# The pace assumed before the model has analysed anything (about five jobs a minute, ADR-077).
_DEFAULT_SECONDS_PER_JOB = 12.0


@dataclass(frozen=True)
class ReextractionPreview:
    """What analysing the open jobs again would involve."""

    candidates: int
    model: str
    seconds_per_job: float
    minutes: int


class ReextractionService:
    """Counts and queues the analyses the owner asks for. The caller commits."""

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] | None = None) -> None:
        self._session = session
        self._extractions = ExtractionRepository(session)
        self._providers = ProviderRepository(session)
        self._schedule = ScheduleRepository(session)
        self._clock = clock or (lambda: datetime.now(UTC))

    async def _criteria(self, owner_id: int, since_days: int) -> dict[str, object]:
        connection = next(
            (c for c in await self._providers.list(owner_id) if c.use_for_jobs and c.model_id),
            None,
        )
        if connection is None or connection.model_id is None:
            msg = "Choose the model that analyses jobs in AI & privacy first."
            raise ConflictError(msg)
        return {
            "provider": connection.provider_type,
            "model": connection.model_id,
            "prompt_version": EXTRACTION_PROMPT_VERSION,
            "accepted_prompt_versions": EXTRACTION_ACCEPTED_PROMPT_VERSIONS,
            "since": self._clock() - timedelta(days=since_days),
            "set_aside_below": await self._schedule.set_aside_below_fit(owner_id),
        }

    async def preview(self, owner_id: int, since_days: int) -> ReextractionPreview:
        """Count the jobs that would be analysed again and estimate the time it takes."""
        criteria = await self._criteria(owner_id, since_days)
        count = await self._extractions.count_reextractions(**criteria)
        seconds = await self._extractions.average_latency_seconds(
            provider=str(criteria["provider"]), model=str(criteria["model"])
        )
        pace = seconds if seconds and seconds > 0 else _DEFAULT_SECONDS_PER_JOB
        return ReextractionPreview(
            candidates=count,
            model=str(criteria["model"]),
            seconds_per_job=pace,
            minutes=math.ceil(count * pace / 60) if count else 0,
        )

    async def queue(self, owner_id: int, since_days: int) -> int:
        """Queue the analyses; the worker takes them like any other. Returns how many."""
        criteria = await self._criteria(owner_id, since_days)
        return await self._extractions.requeue_for_reextraction(
            taxonomy_version_id=await self._extractions.current_taxonomy_version_id(), **criteria
        )
