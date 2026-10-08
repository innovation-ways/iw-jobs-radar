"""Collecting sources: request a run, execute it source by source, ingest what each source returned.

Every source is processed on its own: a network call outside any database transaction, then one
short transaction that stores postings, snapshots, change events and the run result. One source
failing never stops the others, and a failed run never closes anything (document 14, T2).
"""

import logging
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.sources.base import (
    CollectionResult,
    JobSourceAdapter,
    SourceCheckpoint,
    SourceError,
)
from jobs_radar.core.errors import InputValidationError, NotFoundError
from jobs_radar.db.models import CollectionRun, SourceConfiguration, SourceRunResult
from jobs_radar.domain.enums import (
    RunStatus,
    RunTrigger,
    SourceErrorClass,
    SourceOutcome,
    SourceType,
)
from jobs_radar.domain.job_content import MATERIAL_FIELDS, changed_fields, content_hash
from jobs_radar.repositories.jobs import JobRepository
from jobs_radar.repositories.runs import RunRepository
from jobs_radar.repositories.sources import SourceRepository
from jobs_radar.schemas.job import NormalisedJob
from jobs_radar.services.inbox import InboxService
from jobs_radar.services.normalise import build_normalised_job, material_of_job

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
Clock = Callable[[], datetime]

_RUN_MISSING = "Collection run not found."
_OK = {SourceOutcome.SUCCESS, SourceOutcome.NOT_MODIFIED}


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _SourceView:
    """What a run needs to know about a source, copied out so no session is held while fetching."""

    source_configuration_id: int
    source_type: SourceType
    company_id: int
    checkpoint: SourceCheckpoint


@dataclass
class _Counts:
    collected: int = 0
    new: int = 0
    updated: int = 0
    deduplicated: int = 0
    closed: int = 0


class CollectionService:
    """Requests and executes collection runs."""

    def __init__(
        self,
        session_factory: SessionFactory,
        adapters: Mapping[SourceType, JobSourceAdapter],
        *,
        clock: Clock = _utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._adapters = adapters
        self._clock = clock

    # --- requesting and finishing runs ---------------------------------------------------------

    async def request_run(
        self, owner_id: int, *, source_configuration_id: int | None = None
    ) -> CollectionRun:
        """Queue a run of one source, or of every enabled source when none is given.

        Raises:
            NotFoundError: the requested source does not exist.
            InputValidationError: an all-sources run was requested but no source is enabled.
        """
        async with self._session_factory() as session:
            sources = SourceRepository(session)
            if source_configuration_id is not None:
                await sources.get(owner_id, source_configuration_id)
            elif not await sources.list_for_owner(owner_id, only_enabled=True):
                msg = "There is no enabled source to collect. Enable or add a source first."
                raise InputValidationError(msg)
            run = await RunRepository(session).create(
                owner_id, RunTrigger.MANUAL, source_configuration_id=source_configuration_id
            )
            await session.commit()
            return run

    async def list_runs(
        self, owner_id: int, *, limit: int, before_id: int | None
    ) -> tuple[list[tuple[CollectionRun, list[SourceRunResult]]], int | None]:
        """Return a page of runs (newest first) with results, and the cursor for the next page."""
        async with self._session_factory() as session:
            repository = RunRepository(session)
            runs = await repository.list_page(owner_id, limit=limit + 1, before_id=before_id)
            more = len(runs) > limit
            runs = runs[:limit]
            results = await repository.results_for([run.collection_run_id for run in runs])
            page = [(run, results[run.collection_run_id]) for run in runs]
            return page, (runs[-1].collection_run_id if more and runs else None)

    async def get_run(
        self, owner_id: int, collection_run_id: int
    ) -> tuple[CollectionRun, list[SourceRunResult]]:
        """Return one run with its results."""
        async with self._session_factory() as session:
            repository = RunRepository(session)
            run = await repository.get(owner_id, collection_run_id)
            return run, (await repository.results_for([collection_run_id]))[collection_run_id]

    async def fail_interrupted_runs(self) -> int:
        """Mark runs left over from a previous process as failed; returns how many."""
        async with self._session_factory() as session:
            count = await RunRepository(session).fail_interrupted(self._clock())
            await session.commit()
            return count

    async def execute_run(self, collection_run_id: int) -> None:
        """Execute a queued run; a run that is not queued (already taken or finished) is ignored."""
        async with self._session_factory() as session:
            run = await RunRepository(session).claim(collection_run_id, self._clock())
            await session.commit()
            if run is None:
                return
            owner_id, scoped_to = run.owner_id, run.source_configuration_id
        async with self._session_factory() as session:
            sources = SourceRepository(session)
            if scoped_to is not None:
                source_ids = [(await sources.get(owner_id, scoped_to)).source_configuration_id]
            else:
                source_ids = [
                    s.source_configuration_id
                    for s in await sources.list_for_owner(owner_id, only_enabled=True)
                ]

        outcomes = [
            await self._process_source(collection_run_id, source_id) for source_id in source_ids
        ]

        if all(outcome in _OK for outcome in outcomes):
            status = RunStatus.SUCCEEDED
        elif not any(outcome in _OK for outcome in outcomes):
            status = RunStatus.FAILED
        else:
            status = RunStatus.PARTIAL
        async with self._session_factory() as session:
            repository = RunRepository(session)
            current = await session.get(CollectionRun, collection_run_id)
            if current is None:  # pragma: no cover - the run was claimed above
                raise NotFoundError(_RUN_MISSING)
            await repository.finish(current, status, self._clock())
            await session.commit()

    # --- one source ----------------------------------------------------------------------

    async def _load_view(self, collection_run_id: int, source_configuration_id: int) -> _SourceView:
        async with self._session_factory() as session:
            run = await session.get(CollectionRun, collection_run_id)
            if run is None:  # pragma: no cover - the run was claimed by the caller
                raise NotFoundError(_RUN_MISSING)
            source = await SourceRepository(session).get(run.owner_id, source_configuration_id)
            return _SourceView(
                source_configuration_id=source.source_configuration_id,
                source_type=SourceType(source.source_type),
                company_id=int(source.company_id or 0),
                checkpoint=SourceCheckpoint(
                    identifier=source.external_identifier,
                    url=source.url,
                    etag=source.etag,
                    rate_limit_per_minute=source.rate_limit_per_minute,
                ),
            )

    async def _process_source(
        self, collection_run_id: int, source_configuration_id: int
    ) -> SourceOutcome:
        view = await self._load_view(collection_run_id, source_configuration_id)
        started = self._clock()
        adapter = self._adapters.get(view.source_type)
        failure: tuple[SourceErrorClass, str, int | None] | None = None
        fetched: CollectionResult | None = None
        if adapter is None:
            failure = (SourceErrorClass.CONFIGURATION, "This source type is not supported.", None)
        else:
            try:
                fetched = await adapter.collect(view.checkpoint)
            except SourceError as error:
                failure = (error.error_class, error.message, error.http_status)
            # Intentionally broad: a failure in one adapter must not stop the other
            # sources. Nothing from the exception (which may hold addresses or payloads) is stored.
            except Exception:
                logger.exception(
                    "source_collect_crashed",
                    extra={"source_configuration_id": source_configuration_id},
                )
                failure = (
                    SourceErrorClass.UNKNOWN,
                    "Unexpected error while collecting this source.",
                    None,
                )

        if fetched is not None:
            try:
                return await self._store_success(collection_run_id, view, fetched, started)
            # Intentionally broad, for the same reason: record the failure and carry on.
            except Exception:
                logger.exception(
                    "source_ingest_failed",
                    extra={"source_configuration_id": source_configuration_id},
                )
                failure = (
                    SourceErrorClass.UNKNOWN,
                    "Unexpected error while storing this source's jobs.",
                    None,
                )

        assert failure is not None  # noqa: S101  # either the fetch or the ingest failed above
        await self._store_failure(collection_run_id, view, started, failure)
        return SourceOutcome.FAILED

    async def _store_failure(
        self,
        collection_run_id: int,
        view: _SourceView,
        started: datetime,
        failure: tuple[SourceErrorClass, str, int | None],
    ) -> None:
        error_class, message, http_status = failure
        async with self._session_factory() as session:
            finished = self._clock()
            await RunRepository(session).add_result(
                collection_run_id=collection_run_id,
                source_configuration_id=view.source_configuration_id,
                started_at=started,
                finished_at=finished,
                outcome=SourceOutcome.FAILED,
                http_status=http_status,
                error_class=error_class.value,
                error_message=message,
                duration_ms=int((finished - started).total_seconds() * 1000),
            )
            await session.commit()

    async def _store_success(
        self,
        collection_run_id: int,
        view: _SourceView,
        fetched: CollectionResult,
        started: datetime,
    ) -> SourceOutcome:
        async with self._session_factory() as session:
            runs, jobs = RunRepository(session), JobRepository(session)
            previous_success = await runs.last_successful_started_at(view.source_configuration_id)
            counts = _Counts()
            if fetched.outcome == "not_modified":
                touched = await jobs.touch_open_postings(view.source_configuration_id, started)
                counts.collected = counts.deduplicated = touched
                outcome = SourceOutcome.NOT_MODIFIED
            else:
                counts = await self._ingest(session, view, fetched, started, previous_success)
                outcome = SourceOutcome.SUCCESS
            source = await session.get(SourceConfiguration, view.source_configuration_id)
            if source is not None:
                source.etag = fetched.etag
            finished = self._clock()
            await runs.add_result(
                collection_run_id=collection_run_id,
                source_configuration_id=view.source_configuration_id,
                started_at=started,
                finished_at=finished,
                outcome=outcome,
                collected_count=counts.collected,
                new_count=counts.new,
                updated_count=counts.updated,
                deduplicated_count=counts.deduplicated,
                closed_count=counts.closed,
                http_status=fetched.http_status,
                duration_ms=int((finished - started).total_seconds() * 1000),
            )
            await session.commit()
            return outcome

    async def _ingest(
        self,
        session: AsyncSession,
        view: _SourceView,
        fetched: CollectionResult,
        started: datetime,
        previous_success: datetime | None,
    ) -> _Counts:
        jobs = JobRepository(session)
        source = await session.get(SourceConfiguration, view.source_configuration_id)
        if source is None:  # pragma: no cover - loaded moments earlier
            msg = "Source not found."
            raise NotFoundError(msg)
        counts = _Counts(collected=len(fetched.postings))
        seen: set[str] = set()
        for posting in fetched.postings:
            seen.add(posting.external_job_id)
            job = build_normalised_job(
                posting, company_id=view.company_id, source_type=view.source_type
            )
            material = material_of_job(job)
            new_hash = content_hash(material)

            existing = await jobs.find_posting(
                view.source_configuration_id, posting.external_job_id
            )
            previous_snapshot = (
                await jobs.latest_snapshot(existing.job_posting_id) if existing else None
            )
            upsert = await jobs.upsert_posting(
                source,
                external_job_id=posting.external_job_id,
                source_url=posting.source_url,
                title=posting.title,
                content_hash=new_hash,
                seen_at=started,
            )
            snapshot, snapshot_created = await jobs.add_snapshot_if_new(
                upsert.posting,
                content_hash=new_hash,
                fetched_at=started,
                raw_payload=posting.raw_payload,
                normalised=job.model_dump(mode="json"),
            )
            content_changed = not upsert.created and upsert.previous_content_hash != new_hash
            if upsert.created:
                counts.new += 1
            elif content_changed:
                counts.updated += 1
                # a material source change moves eligible inbox items to updated_unread
                await InboxService(session).notify_material_change(upsert.posting.job_posting_id)
                previous_material = (
                    material_of_job(NormalisedJob.model_validate(previous_snapshot.normalised_json))
                    if previous_snapshot is not None
                    else dict.fromkeys(MATERIAL_FIELDS)
                )
                await jobs.add_change_event(
                    upsert.posting,
                    from_snapshot=previous_snapshot,
                    to_snapshot=snapshot,
                    changed_fields=changed_fields(previous_material, material),
                )
            elif upsert.reopened:
                counts.updated += 1  # a job that came back is news even if its text did not change
            else:
                counts.deduplicated += 1
            del snapshot_created  # creation is implied by content_changed / created

        counts.closed = await jobs.close_unseen(
            view.source_configuration_id,
            seen,
            previous_success_started_at=previous_success,
            closed_at=started,
        )
        return counts
