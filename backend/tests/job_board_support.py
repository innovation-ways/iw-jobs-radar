"""Shared helpers for the job-board adapter tests: a guarded client, a fixed clock, scripted routes."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from jobs_radar.adapters.sources.base import RateLimiter, SourceCheckpoint
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.core.url_guard import UrlGuard
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def payload(folder: str, name: str) -> bytes:
    """Bytes of a synthetic recorded answer."""
    return (FIXTURES / folder / name).read_bytes()


class Sleeper:
    """Records the waits the adapter asks for instead of sleeping."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def clock() -> datetime:
    """The fixed 'now' of the fixtures."""
    return NOW


def build(adapter_class: Callable[..., Any], sleeper: Sleeper | None = None) -> Any:
    """Create an adapter on a guarded client that resolves every host to a public address."""

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    client = GuardedHttpClient(guard=UrlGuard(resolver=resolve), user_agent="JobsRadar/test")
    sleeper = sleeper or Sleeper()
    return adapter_class(
        client, sleep=sleeper, limiter=RateLimiter(sleep=sleeper, clock=lambda: 0.0), clock=clock
    )


PORTUGAL = LocationScope(frozenset({"PT"}), include_worldwide=True)


def checkpoint(
    identifier: str,
    filters: JobBoardFilters | None = None,
    scope: LocationScope | None = PORTUGAL,
) -> SourceCheckpoint:
    """A checkpoint for a job board source; the scope is what the profile and intents give."""
    return SourceCheckpoint(
        identifier=identifier,
        url=f"https://example.test/{identifier}",
        etag=None,
        rate_limit_per_minute=60,
        filters=filters,
        scope=scope,
    )


class Scripted:
    """A respx side effect: answers by the query parameters of the request and records the calls.

    ``routes`` is a list of ``(wanted_params, status, body)``; the first whose parameters are all
    present in the request answers. A request nobody expects gets a 599, so a wrong URL fails loudly.
    """

    def __init__(self, routes: list[tuple[dict[str, str], int, bytes]]) -> None:
        self._routes = routes
        self.calls: list[dict[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.calls.append(params)
        for wanted, status, body in self._routes:
            if all(params.get(key) == value for key, value in wanted.items()):
                return httpx.Response(status, content=body)
        return httpx.Response(599, content=b"unexpected request")
