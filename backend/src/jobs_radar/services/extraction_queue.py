"""The extraction queue: queue missing extractions, claim them and run them (T4.4, ADR-039).

Collection never waits for AI. The worker calls :meth:`ExtractionQueue.enqueue_missing` and then
:meth:`ExtractionQueue.run_batch`, which processes waiting jobs for a bounded time so the worker's
heartbeat stays fresh. Every job is its own short transaction; the model call happens outside any
transaction. Without a reachable model the jobs simply stay waiting ("not evaluated").
"""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.providers.base import ExtractionProvider
from jobs_radar.db.models import JobExtraction, JobSnapshot
from jobs_radar.domain.enums import EXTRACTION_PROMPT_VERSION
from jobs_radar.repositories.extractions import ExtractionRepository
from jobs_radar.repositories.taxonomy import TaxonomyRepository
from jobs_radar.services.extraction import (
    ExtractionError,
    ExtractionInput,
    ExtractionResult,
    JobExtractor,
)
from jobs_radar.services.locations import resolve_all
from jobs_radar.services.skills import SkillCanonicaliser

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
Clock = Callable[[], datetime]
Heartbeat = Callable[[], Awaitable[None]]

MAX_ATTEMPTS = 3
# A claim older than this belongs to a worker that died; the job is taken again.
CLAIM_TIMEOUT = timedelta(minutes=10)


@dataclass(frozen=True)
class BatchSummary:
    """What one batch did. ``stopped`` means the provider was unavailable and the batch ended.

    ``backlog`` is true when the time budget ended the batch while jobs were still waiting.
    """

    succeeded: int
    failed: int
    stopped: bool
    backlog: bool = False


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _hints(snapshot: JobSnapshot) -> dict[str, list[str]]:
    """Return the source's own structured fields (given to the model first, compared afterwards)."""
    normalised: dict[str, Any] = snapshot.normalised_json
    locations = [
        loc["raw"]
        for loc in normalised.get("work_arrangement", {}).get("locations", [])
        if loc.get("raw")
    ]
    payload = snapshot.raw_payload_json if isinstance(snapshot.raw_payload_json, dict) else {}
    departments = [
        d["name"] for d in payload.get("departments") or [] if isinstance(d, dict) and d.get("name")
    ]
    return {"locations": locations, "departments": departments}


def _resolved_locations(
    result: ExtractionResult, hints: dict[str, list[str]]
) -> list[dict[str, Any]]:
    """Resolve the extracted places (else the source's own) offline."""
    attribute = result.output.locations
    raws = (
        attribute.value if attribute.status == "known" and attribute.value else hints["locations"]
    )
    return resolve_all(raws)


class ExtractionQueue:
    """Queues and runs AI extractions for collected jobs."""

    def __init__(
        self,
        session_factory: SessionFactory,
        provider: ExtractionProvider,
        *,
        max_chars: int,
        clock: Clock = _utc_now,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._max_chars = max_chars
        self._clock = clock
        self._max_attempts = max_attempts

    async def enqueue_missing(self, limit: int = 500) -> int:
        """Queue the latest snapshots of open postings that have no extraction yet."""
        async with self._session_factory() as session:
            repository = ExtractionRepository(session)
            queued = await repository.enqueue_missing(
                provider=self._provider.provider,
                model=self._provider.model,
                prompt_version=EXTRACTION_PROMPT_VERSION,
                taxonomy_version_id=await repository.current_taxonomy_version_id(),
                limit=limit,
            )
            await session.commit()
            return queued

    async def run_batch(
        self, *, budget_seconds: float = 45.0, heartbeat: Heartbeat | None = None
    ) -> BatchSummary:
        """Process waiting jobs until none are left, the time budget is spent or the model is down.

        A job whose attempt failed is not retried within the same batch.
        """
        deadline = self._clock() + timedelta(seconds=budget_seconds)
        async with self._session_factory() as session:
            taxonomy = await TaxonomyRepository(session).keys_by_kind()
        extractor = JobExtractor(self._provider, taxonomy, max_chars=self._max_chars)
        succeeded = failed = 0
        seen: set[int] = set()
        backlog = False
        while True:
            if self._clock() >= deadline:
                backlog = True
                break
            claimed = await self._claim(seen)
            if claimed is None:
                break
            extraction_id, job, hints = claimed
            seen.add(extraction_id)
            outcome = await self._process(extractor, extraction_id, job, hints)
            if outcome == "stopped":
                return BatchSummary(succeeded, failed, stopped=True)
            succeeded += outcome == "succeeded"
            failed += outcome == "failed"
            if heartbeat is not None:
                await heartbeat()
        return BatchSummary(succeeded, failed, stopped=False, backlog=backlog)

    async def _claim(
        self, seen: set[int]
    ) -> tuple[int, ExtractionInput, dict[str, list[str]]] | None:
        now = self._clock()
        async with self._session_factory() as session:
            claimed = await ExtractionRepository(session).claim_next(
                provider=self._provider.provider,
                model=self._provider.model,
                prompt_version=EXTRACTION_PROMPT_VERSION,
                now=now,
                stale_before=now - CLAIM_TIMEOUT,
                exclude=seen,
            )
            await session.commit()
            if claimed is None:
                return None
            extraction, snapshot = claimed
            hints = _hints(snapshot)
            job = ExtractionInput(
                title=snapshot.normalised_json["title"],
                description=snapshot.normalised_json["description_text"],
                hints=hints,
            )
            return extraction.job_extraction_id, job, hints

    async def _process(
        self,
        extractor: JobExtractor,
        extraction_id: int,
        job: ExtractionInput,
        hints: dict[str, list[str]],
    ) -> str:
        try:
            result = await extractor.extract(job)
        except ExtractionError as error:
            return await self._record_failure(extraction_id, error)
        async with self._session_factory() as session:
            repository = ExtractionRepository(session)
            extraction = await repository.get(extraction_id)
            attributes = result.stored_attributes()
            resolved = await SkillCanonicaliser(session).canonicalise(result.output.skills)
            attributes["skills_resolved"] = [
                {"skill_id": s.skill_id, "name": s.name, "importance": s.importance}
                for s in resolved
            ]
            attributes["locations_resolved"] = _resolved_locations(result, hints)
            await repository.finalise_success(
                extraction,
                attributes=attributes,
                truncated=result.truncated,
                latency_ms=result.latency_ms,
                now=self._clock(),
            )
            await session.commit()
        return "succeeded"

    async def _record_failure(self, extraction_id: int, error: ExtractionError) -> str:
        async with self._session_factory() as session:
            repository = ExtractionRepository(session)
            extraction: JobExtraction = await repository.get(extraction_id)
            if not error.counts_as_attempt:
                # The provider is unreachable or misconfigured: the job waits, no attempt is used.
                await repository.release(extraction, error.error_class)
                await session.commit()
                return "stopped"
            final = await repository.record_attempt(
                extraction,
                error_class=error.error_class,
                now=self._clock(),
                max_attempts=self._max_attempts,
                detail=error.detail,
            )
            await session.commit()
            return "failed" if final else "retry"
