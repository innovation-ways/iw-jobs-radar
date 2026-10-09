"""Contracts shared by every job source adapter (HLD section 6, ADR-035).

An adapter turns one source's API into :class:`SourcePosting` values. It never touches the database
and never decides fit or inbox state; it only fetches, validates and maps.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from jobs_radar.core.http import FetchError
from jobs_radar.domain.enums import SourceErrorClass, SourceType


class SourceError(Exception):
    """Collecting or validating a source failed. ``error_class`` is a stable reason."""

    def __init__(
        self, error_class: SourceErrorClass, message: str, *, http_status: int | None = None
    ) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.message = message
        self.http_status = http_status


_FETCH_CLASSES = {
    "timeout": SourceErrorClass.TIMEOUT,
    "network_error": SourceErrorClass.NETWORK_ERROR,
    "too_many_redirects": SourceErrorClass.NETWORK_ERROR,
    "too_large": SourceErrorClass.TOO_LARGE,
    "blocked_url": SourceErrorClass.BLOCKED_URL,
}


def source_error_from_fetch(error: FetchError) -> SourceError:
    """Translate a transport-level failure into a source error."""
    return SourceError(
        _FETCH_CLASSES.get(error.error_class, SourceErrorClass.UNKNOWN),
        error.message,
        http_status=error.http_status,
    )


@dataclass(frozen=True)
class SourceCheckpoint:
    """What an adapter needs to know about one configured source."""

    identifier: str
    url: str
    etag: str | None
    rate_limit_per_minute: int


@dataclass(frozen=True)
class BoardInfo:
    """Result of validating a board before it is saved."""

    name: str
    postings_count: int


@dataclass(frozen=True)
class SourcePosting:
    """One posting as obtained from a source, with the description already reduced to safe text."""

    external_job_id: str
    title: str
    source_url: str
    apply_url: str
    description_text: str
    locations: tuple[str, ...]
    posted_at: datetime | None
    source_updated_at: datetime | None
    departments: tuple[str, ...]
    language: str | None
    raw_payload: dict[str, Any]
    # Job boards publish many companies' postings, so the posting names its company (ADR-049.6).
    company_name: str | None = None


@dataclass(frozen=True)
class CollectionResult:
    """Outcome of one collection request."""

    outcome: Literal["modified", "not_modified"]
    postings: tuple[SourcePosting, ...]
    etag: str | None
    http_status: int
    duration_ms: int
    declared_total: int | None


class JobSourceAdapter(Protocol):
    """A source that can be validated and collected."""

    source_type: SourceType

    def endpoint(self, identifier: str) -> str:
        """Return the URL stored in the source configuration for ``identifier``."""
        ...

    async def validate(self, identifier: str) -> BoardInfo:
        """Check that the board exists and describe it. Raises :class:`SourceError`."""
        ...

    async def collect(self, checkpoint: SourceCheckpoint) -> CollectionResult:
        """Fetch the board's current postings. Raises :class:`SourceError`."""
        ...


Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


class RateLimiter:
    """Spaces requests per key so that a source is never called faster than its configured rate."""

    def __init__(self, *, sleep: Sleep = asyncio.sleep, clock: Clock = time.monotonic) -> None:
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}

    async def wait(self, key: str, per_minute: int) -> None:
        """Wait until ``key`` may make another request, then record it."""
        interval = 60.0 / max(per_minute, 1)
        last = self._last.get(key)
        if last is not None:
            remaining = interval - (self._clock() - last)
            if remaining > 0:
                await self._sleep(remaining)
        self._last[key] = self._clock()
