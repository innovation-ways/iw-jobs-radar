"""Writes and stores the short summaries of jobs with the local model (ADR-059).

Two entry points share the same steps: ``summarise`` (one posting, on demand or for the sample
tool) and ``run_pending`` (the worker: only jobs first seen on or after the cut-off, so the past is
never summarised in bulk). A summary is stored once per snapshot, model and prompt; an answer that
stays unusable is stored as a failed attempt so the worker does not ask again; a model that is
down raises :class:`SummaryUnavailable` and stores nothing, so the job simply waits.
"""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.providers.base import ExtractionProvider
from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import Company, JobPosting, JobSnapshot
from jobs_radar.domain.enums import SUMMARIES_FROM, SUMMARY_PROMPT_VERSION, SummaryStatus
from jobs_radar.repositories.summaries import SummaryRepository
from jobs_radar.services.summary_writer import SummaryError, SummaryWriter

logger = structlog.get_logger()


class SummaryUnavailable(Exception):  # noqa: N818  # a condition, like DirectionUnavailable
    """The model could not be reached or answered too slowly; nothing was stored."""


@dataclass(frozen=True)
class SummaryResult:
    """The summary of a posting; ``text`` is ``None`` when the model's answer was unusable."""

    text: str | None
    created: bool


class SummaryService:
    """Writes and stores summaries. The caller owns the transaction."""

    def __init__(
        self, session: AsyncSession, provider: ExtractionProvider, *, max_chars: int
    ) -> None:
        self._session = session
        self._provider = provider
        self._writer = SummaryWriter(provider, max_chars=max_chars)
        self._repo = SummaryRepository(session)

    async def _summarise_snapshot(self, job_posting_id: int, snapshot_id: int) -> SummaryResult:
        have = await self._repo.latest_success(
            snapshot_id,
            provider=self._provider.provider,
            model=self._provider.model,
            prompt_version=SUMMARY_PROMPT_VERSION,
        )
        if have is not None:
            return SummaryResult(have.summary_text, created=False)
        posting = await self._session.get(JobPosting, job_posting_id)
        snapshot = await self._session.get(JobSnapshot, snapshot_id)
        assert posting is not None and snapshot is not None  # noqa: S101  # ids come from queries
        company = await self._session.get(Company, posting.company_id)
        normalised = snapshot.normalised_json
        status, text, error_class, latency = SummaryStatus.SUCCEEDED, None, None, None
        try:
            outcome = await self._writer.write(
                company=company.canonical_name if company else "",
                title=normalised["title"],
                description=normalised["description_text"],
            )
            text, latency = outcome.text, outcome.latency_ms
        except SummaryError as error:
            if error.error_class != "invalid_output":
                # Down, missing model, timeout...: says nothing about the job, so try later.
                raise SummaryUnavailable(error.message) from error
            status, error_class = SummaryStatus.FAILED, error.error_class
        stored = await self._repo.add(
            job_snapshot_id=snapshot_id,
            provider=self._provider.provider,
            model=self._provider.model,
            prompt_version=SUMMARY_PROMPT_VERSION,
            status=status,
            summary_text=text,
            error_class=error_class,
            latency_ms=latency,
        )
        return SummaryResult(text, created=stored and text is not None)

    async def summarise(self, job_posting_id: int) -> SummaryResult:
        """Return the summary of the posting's latest snapshot, writing it if it is missing.

        Raises:
            NotFoundError: unknown posting.
            SummaryUnavailable: the model could not be reached.
        """
        snapshot_id = await self._repo.latest_snapshot_id(job_posting_id)
        if snapshot_id is None:
            msg = "Job posting not found."
            raise NotFoundError(msg)
        return await self._summarise_snapshot(job_posting_id, snapshot_id)

    async def run_pending(self, since: datetime, *, limit: int = 1) -> int:
        """Summarise open jobs first seen at or after ``since``; return how many were attempted."""
        done = 0
        for job_posting_id in await self._repo.pending(SUMMARY_PROMPT_VERSION, since, limit):
            snapshot_id = await self._repo.latest_snapshot_id(job_posting_id)
            if snapshot_id is None:
                continue
            await self._summarise_snapshot(job_posting_id, snapshot_id)
            done += 1
        return done


class SummaryRunner:
    """Summarises new jobs for the worker, one short transaction per job (ADR-059)."""

    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        provider: ExtractionProvider,
        *,
        max_chars: int,
        since: datetime = SUMMARIES_FROM,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._max_chars = max_chars
        self._since = since
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def model(self) -> str:
        """The model that writes the summaries."""
        return self._provider.model

    async def run(
        self,
        limit: int = 50,
        *,
        budget_seconds: float = 45.0,
        heartbeat: Callable[[], Awaitable[None]] | None = None,
    ) -> int:
        """Summarise pending jobs for a bounded time and return how many were done.

        A model that is down ends the batch quietly: the jobs wait and are never marked as
        failed, and the rest of the worker's iteration carries on.
        """
        deadline = self._clock() + timedelta(seconds=budget_seconds)
        done = 0
        while done < limit and self._clock() < deadline:
            async with self._session_factory() as session:
                service = SummaryService(session, self._provider, max_chars=self._max_chars)
                try:
                    attempted = await service.run_pending(self._since, limit=1)
                except SummaryUnavailable:
                    logger.warning("summaries_model_unavailable")
                    break
                await session.commit()
            if attempted == 0:
                break
            done += attempted
            if heartbeat is not None:
                await heartbeat()
        return done
