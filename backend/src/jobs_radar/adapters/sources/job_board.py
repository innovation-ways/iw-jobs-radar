"""Shared behaviour of the job-board adapters (ADR-049, research R-00173).

A job board is one source with the postings of many companies. Each adapter only knows how to read
its own board into :class:`Candidate` values, page by page; this base class applies the owner's
filters before anything is stored, enforces the per-run limit, removes repeats and reports how many
postings were dropped and whether the run stopped early (a truncated run never closes postings,
ADR-049.5).
"""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from jobs_radar.adapters.sources.base import (
    BoardInfo,
    CollectionResult,
    RateLimiter,
    SourceCheckpoint,
    SourceError,
    SourcePosting,
)
from jobs_radar.adapters.sources.catalogue import CatalogueEntry, get_entry
from jobs_radar.adapters.sources.polite_http import PoliteGetter
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import (
    Eligibility,
    LocationCandidate,
    LocationScope,
    allows_location,
    categorise,
    is_recent,
    matches_terms,
)
from jobs_radar.schemas.source_filters import JobBoardFilters

# Safety net against a feed that never ends; the per-run limit normally stops the scan first.
MAX_PAGES_PER_STREAM = 100
# The add-board preview scans only this many kept postings, so it answers within seconds.
PREVIEW_LIMIT = 100


class MalformedPostingError(Exception):
    """One posting of a feed lacks what is needed; it is skipped and counted, not fatal."""


@dataclass(frozen=True)
class Candidate:
    """A posting as read from the board, with what the filters need to judge it."""

    posting: SourcePosting
    eligibility: Eligibility
    area_texts: tuple[str, ...]
    # Remote or on-site, as the board says; boards that list only remote work say True.
    remote: bool | None = True
    place: tuple[float, float] | None = None


@dataclass(frozen=True)
class Page:
    """One page of a stream: its candidates, whether more follow and the board's declared total."""

    candidates: list[Candidate]
    skipped: int = 0
    has_more: bool = False
    declared_total: int | None = None
    # The stream itself stopped reading before the end of what it found (a page cap): the run
    # did not see every posting, so it must not close postings (ADR-049.5).
    capped: bool = False


# A stream is a source of pages (for example "jobs open to Europe"); it is closed early when the
# board lists newest first and a page only holds postings older than the age limit.
Stream = Callable[[], AsyncIterator[Page]]


@dataclass
class _Scan:
    kept: list[SourcePosting]
    dropped: int
    declared_total: int | None
    seen: int
    truncated: bool


class JobBoardAdapter:
    """Base class of the job-board adapters. Subclasses set ``entry`` and implement ``_streams``."""

    entry: CatalogueEntry
    source_type: SourceType
    newest_first = True

    def __init__(
        self,
        client: GuardedHttpClient,
        *,
        sleep: Any = asyncio.sleep,
        limiter: RateLimiter | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._getter = PoliteGetter(
            client,
            sleep=sleep,
            limiter=limiter,
            not_found_message="The job board could not be found.",
            auth_statuses=frozenset({401, 403}),
        )
        self._clock = clock

    def endpoint(self, identifier: str) -> str:
        """Return the catalogue endpoint; an identifier other than the catalogue key is refused."""
        self._check(identifier)
        return self.entry.endpoint

    def _check(self, identifier: str) -> None:
        if identifier != self.entry.catalogue_key or get_entry(identifier) is None:
            msg = "Unknown job board."
            raise SourceError(SourceErrorClass.CONFIGURATION, msg)

    def _streams(
        self,
        filters: JobBoardFilters,
        scope: LocationScope,
        *,
        per_minute: int,
        credential: str | None,
    ) -> list[Stream]:
        raise NotImplementedError

    async def validate(
        self,
        identifier: str,
        credential: str | None = None,
        filters: JobBoardFilters | None = None,
        scope: LocationScope | None = None,
    ) -> BoardInfo:
        """Scan a bounded sample of the board and report how many postings match the filters."""
        self._check(identifier)
        filters = filters or self.entry.default_filters
        limit = min(filters.max_postings_per_run, PREVIEW_LIMIT)
        scan = await self._scan(
            filters,
            self._require_scope(scope),
            limit,
            per_minute=self.entry.rate_limit_per_minute,
            credential=credential,
        )
        return BoardInfo(
            name=self.entry.display_name,
            postings_count=scan.declared_total or scan.seen,
            matching_count=len(scan.kept),
            matching_is_lower_bound=scan.truncated,
        )

    async def collect(self, checkpoint: SourceCheckpoint) -> CollectionResult:
        """Fetch the board's postings that pass the filters, up to the per-run limit."""
        self._check(checkpoint.identifier)
        filters = checkpoint.filters or self.entry.default_filters
        started = asyncio.get_running_loop().time()
        scan = await self._scan(
            filters,
            self._require_scope(checkpoint.scope),
            filters.max_postings_per_run,
            per_minute=checkpoint.rate_limit_per_minute,
            credential=checkpoint.credential,
        )
        duration_ms = int((asyncio.get_running_loop().time() - started) * 1000)
        return CollectionResult(
            "modified",
            tuple(scan.kept),
            None,
            200,
            duration_ms,
            scan.declared_total,
            dropped_count=scan.dropped,
            truncated=scan.truncated,
        )

    # --- scanning and filtering ------------------------------------------------------------------

    @staticmethod
    def _require_scope(scope: LocationScope | None) -> LocationScope:
        """Refuse to collect when the owner's location is unknown: nothing could be filtered."""
        if scope is None or scope.is_empty:
            msg = "Set your base location and remote regions in Profile & intent first."
            raise SourceError(SourceErrorClass.CONFIGURATION, msg)
        return scope

    async def _scan(
        self,
        filters: JobBoardFilters,
        scope: LocationScope,
        limit: int,
        *,
        per_minute: int,
        credential: str | None,
    ) -> _Scan:
        now = self._clock()
        scan = _Scan([], 0, None, 0, False)
        ids: set[str] = set()
        for stream in self._streams(filters, scope, per_minute=per_minute, credential=credential):
            pages = stream()
            try:
                if await self._read_stream(pages, filters, scope, limit, now, scan, ids):
                    return scan
            finally:
                await pages.aclose()  # type: ignore[attr-defined]  # async generators have aclose
        return scan

    async def _read_stream(
        self,
        pages: AsyncIterator[Page],
        filters: JobBoardFilters,
        scope: LocationScope,
        limit: int,
        now: datetime,
        scan: _Scan,
        ids: set[str],
    ) -> bool:
        """Read one stream into ``scan``; return True when the whole scan must stop (limit hit)."""
        async for page in pages:
            if page.declared_total is not None:
                scan.declared_total = (scan.declared_total or 0) + page.declared_total
            scan.dropped += page.skipped
            scan.seen += page.skipped
            if page.capped:
                scan.truncated = True
            all_old = bool(page.candidates)
            for index, candidate in enumerate(page.candidates):
                posting = candidate.posting
                if posting.external_job_id in ids:
                    continue
                ids.add(posting.external_job_id)
                scan.seen += 1
                if is_recent(posting.posted_at, now, filters.max_age_days):
                    all_old = False
                if not self._passes(candidate, filters, scope, now):
                    scan.dropped += 1
                    continue
                if len(scan.kept) >= limit:
                    scan.truncated = True
                    return True
                scan.kept.append(posting)
                if len(scan.kept) >= limit and (page.has_more or index + 1 < len(page.candidates)):
                    scan.truncated = True
                    return True
            if self.newest_first and all_old:
                return False
        return False

    @staticmethod
    def _passes(
        candidate: Candidate, filters: JobBoardFilters, scope: LocationScope, now: datetime
    ) -> bool:
        posting = candidate.posting
        if not posting.company_name:
            return False
        if not is_recent(posting.posted_at, now, filters.max_age_days):
            return False
        where = LocationCandidate(candidate.remote, candidate.eligibility, candidate.place)
        if not allows_location(where, scope):
            return False
        if filters.categories and not set(filters.categories) & categorise(
            (posting.title, *candidate.area_texts)
        ):
            return False
        text = " ".join((posting.title, *candidate.area_texts, posting.description_text))
        return matches_terms(text, filters.search_terms)

    # --- helpers for subclasses -------------------------------------------------------------------

    async def _get_json(
        self, url: str, *, per_minute: int, headers: dict[str, str] | None = None
    ) -> Any:
        """GET ``url`` politely and decode the JSON answer."""
        response = await self._getter.get(
            url, headers or {}, self.entry.catalogue_key, per_minute=per_minute
        )
        try:
            return json.loads(response.body)
        except (ValueError, UnicodeDecodeError) as exc:
            msg = "The answer is not valid JSON."
            raise SourceError(SourceErrorClass.INVALID_PAYLOAD, msg) from exc
