"""Collecting sources: request a run, execute it source by source, ingest what each source returned.

Every source is processed on its own: a network call outside any database transaction, then one
short transaction that stores postings, snapshots, change events and the run result. One source
failing never stops the others, and a failed run never closes anything (document 14, T2).
"""

import logging
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.sources.base import (
    CollectionResult,
    JobSourceAdapter,
    SourceCheckpoint,
    SourceError,
)
from jobs_radar.adapters.sources.catalogue import get_entry
from jobs_radar.core.errors import ConflictError, InputValidationError, NotFoundError
from jobs_radar.db.models import CollectionRun, SourceConfiguration, SourceRunResult
from jobs_radar.domain.enums import (
    RunStatus,
    RunTrigger,
    SourceCategory,
    SourceErrorClass,
    SourceOutcome,
    SourceType,
)
from jobs_radar.domain.job_content import MATERIAL_FIELDS, changed_fields, content_hash
from jobs_radar.domain.sources import next_run_allowed_at, source_category
from jobs_radar.repositories.companies import CompanyRepository
from jobs_radar.repositories.jobs import JobRepository
from jobs_radar.repositories.runs import RunRepository
from jobs_radar.repositories.sources import SourceRepository
from jobs_radar.schemas.job import NormalisedJob
from jobs_radar.schemas.source_filters import JobBoardFilters
from jobs_radar.services.inbox import InboxService
from jobs_radar.services.location_scope import LocationScopeService
from jobs_radar.services.normalise import build_normalised_job, material_of_job

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
Clock = Callable[[], datetime]
Progress = Callable[[], Awaitable[None]]

_RUN_MISSING = "Collection run not found."
# Outcomes that are not a failure; a skipped source (ran too recently) is not one either.
_OK = {SourceOutcome.SUCCESS, SourceOutcome.NOT_MODIFIED, SourceOutcome.SKIPPED}


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _SourceView:
    """What a run needs to know about a source, copied out so no session is held while fetching."""

    source_configuration_id: int
    source_type: SourceType
    company_id: int | None  # empty for a job board: each posting names its company
    checkpoint: SourceCheckpoint
    is_job_board: bool = False
    next_allowed_at: datetime | None = None


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
                source = await sources.get(owner_id, source_configuration_id)
                await self._check_interval(session, source)
            elif not await sources.list_for_owner(owner_id, only_enabled=True):
                msg = "There is no enabled source to collect. Enable or add a source first."
                raise InputValidationError(msg)
            run = await RunRepository(session).create(
                owner_id, RunTrigger.MANUAL, source_configuration_id=source_configuration_id
            )
            await session.commit()
            return run

    async def _check_interval(self, session: AsyncSession, source: SourceConfiguration) -> None:
        """Refuse a manual run of a job board that was contacted less than its minimum ago."""
        entry = (
            get_entry(source.external_identifier)
            if source_category(SourceType(source.source_type)) is SourceCategory.JOB_BOARD
            else None
        )
        if entry is None:
            return
        last = await RunRepository(session).last_attempt_finished_at(source.source_configuration_id)
        allowed = next_run_allowed_at(last, entry.min_interval_minutes)
        if allowed is not None and allowed > self._clock():
            msg = f"{entry.display_name} was contacted recently; try again later."
            raise ConflictError(
                msg, details={"reason": "too_soon", "next_run_allowed_at": allowed.isoformat()}
            )

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

    async def run_queued(self, *, limit: int = 5, on_progress: Progress | None = None) -> int:
        """Execute queued runs, oldest first; returns how many were executed.

        ``on_progress`` is awaited after each source so the worker can keep its heartbeat fresh.
        """
        async with self._session_factory() as session:
            ids = await RunRepository(session).queued_ids(limit)
        for run_id in ids:
            await self.execute_run(run_id, on_progress=on_progress)
        return len(ids)

    async def recover(self) -> int:
        """Fail runs a dead worker left running (retrying scheduled ones); returns how many."""
        return await self._fail_running("interrupted", started_before=None)

    async def fail_stuck_runs(self, max_age: timedelta) -> int:
        """Fail runs that have been running longer than ``max_age``; returns how many."""
        return await self._fail_running("stuck", started_before=self._clock() - max_age)

    async def _fail_running(self, error_class: str, *, started_before: datetime | None) -> int:
        async with self._session_factory() as session:
            repository = RunRepository(session)
            failed = await repository.fail_running(
                self._clock(), error_class, started_before=started_before
            )
            retry_for = next((r for r in failed if r.trigger == RunTrigger.SCHEDULED.value), None)
            if retry_for is not None and not await repository.has_active_run(retry_for.owner_id):
                # An interrupted scheduled run is retried once as a fresh run.
                await repository.create(retry_for.owner_id, RunTrigger.SCHEDULED)
            await session.commit()
            return len(failed)

    async def execute_run(
        self, collection_run_id: int, *, on_progress: Progress | None = None
    ) -> None:
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

        outcomes = []
        for source_id in source_ids:
            outcomes.append(await self._process_source(collection_run_id, source_id))
            if on_progress is not None:
                await on_progress()

        if all(outcome in _OK for outcome in outcomes):
            status = RunStatus.SUCCEEDED
        elif all(outcome is SourceOutcome.FAILED for outcome in outcomes):
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
            source_type = SourceType(source.source_type)
            entry = (
                get_entry(source.external_identifier)
                if source_category(source_type) is SourceCategory.JOB_BOARD
                else None
            )
            filters = scope = next_allowed = None
            if entry is not None:
                # The countries are never typed into a source: they come from the profile and the
                # enabled intents (ADR-049.11).
                filters = (
                    JobBoardFilters.model_validate(source.config_json)
                    if source.config_json
                    else entry.default_filters
                )
                scope = await LocationScopeService(session).for_owner(run.owner_id)
                last = await RunRepository(session).last_attempt_finished_at(
                    source.source_configuration_id
                )
                next_allowed = next_run_allowed_at(last, entry.min_interval_minutes)
            return _SourceView(
                source_configuration_id=source.source_configuration_id,
                source_type=source_type,
                company_id=source.company_id,
                checkpoint=SourceCheckpoint(
                    identifier=source.external_identifier,
                    url=source.url,
                    etag=source.etag,
                    rate_limit_per_minute=source.rate_limit_per_minute,
                    filters=filters,
                    scope=scope,
                ),
                is_job_board=entry is not None,
                next_allowed_at=next_allowed,
            )

    async def _process_source(
        self, collection_run_id: int, source_configuration_id: int
    ) -> SourceOutcome:
        view = await self._load_view(collection_run_id, source_configuration_id)
        started = self._clock()
        adapter = self._adapters.get(view.source_type)
        failure: tuple[SourceErrorClass, str, int | None] | None = None
        fetched: CollectionResult | None = None
        if view.next_allowed_at is not None and view.next_allowed_at > started:
            await self._store_skipped(collection_run_id, view, started)
            return SourceOutcome.SKIPPED
        scope = view.checkpoint.scope
        if view.is_job_board and (scope is None or scope.is_empty):
            msg = "Set your base location and remote regions in Profile & intent first."
            failure = (SourceErrorClass.CONFIGURATION, msg, None)
        elif adapter is None:
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

    async def _store_skipped(
        self, collection_run_id: int, view: _SourceView, started: datetime
    ) -> None:
        """Record that a job board was left alone because it ran less than its minimum ago."""
        allowed = view.next_allowed_at
        async with self._session_factory() as session:
            await RunRepository(session).add_result(
                collection_run_id=collection_run_id,
                source_configuration_id=view.source_configuration_id,
                started_at=started,
                finished_at=self._clock(),
                outcome=SourceOutcome.SKIPPED,
                error_message=(
                    "Ran recently; the next run is allowed at "
                    f"{allowed.isoformat() if allowed else 'a later time'}."
                ),
            )
            await session.commit()

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
                # A run that stopped at its limit saw only part of the board (ADR-049.5).
                outcome = SourceOutcome.PARTIAL if fetched.truncated else SourceOutcome.SUCCESS
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
                dropped_count=fetched.dropped_count,
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
        companies = CompanyRepository(session)
        company_ids: dict[str, int] = {}
        for posting in fetched.postings:
            seen.add(posting.external_job_id)
            company_id = view.company_id
            if company_id is None:
                # A job board names the company of each posting; one lookup per name per run.
                name = posting.company_name
                if not name:
                    counts.collected -= 1
                    continue
                if name not in company_ids:
                    company_ids[name] = (await companies.get_or_create(name)).company_id
                company_id = company_ids[name]
            job = build_normalised_job(posting, company_id=company_id, source_type=view.source_type)
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
                company_id=company_id,
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

        if not fetched.truncated:
            counts.closed = await jobs.close_unseen(
                view.source_configuration_id,
                seen,
                previous_success_started_at=previous_success,
                closed_at=started,
            )
        return counts
