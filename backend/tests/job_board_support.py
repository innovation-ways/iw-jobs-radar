"""Shared helpers for the job-board adapter tests: a guarded client, a fixed clock, scripted routes."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from jobs_radar.adapters.sources.base import RateLimiter, SourceCheckpoint
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.core.url_guard import UrlGuard
from jobs_radar.domain.job_board_rules import LocationScope, OnsiteArea
from jobs_radar.schemas.source_filters import JobBoardFilters
from tests.prefilter_rules import software_rules

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


SOFTWARE_AREAS = ["software", "data", "devops", "security", "telecom"]


def software_filters(filters: JobBoardFilters | None) -> JobBoardFilters:
    """The filters an owner of the software pack gets: all five areas unless the test chose some.

    Before ADR-080 these five areas were the default of ``JobBoardFilters``; now the services fill
    in the owner's areas, so the tests that mean "an owner with the software pack" do the same.
    """
    filters = filters or JobBoardFilters()
    if "categories" in filters.model_fields_set:
        return filters
    return filters.model_copy(update={"categories": list(SOFTWARE_AREAS)})


class _SoftwareOwner:
    """Wraps a job-board adapter so that ``validate`` runs as for an owner with the software pack."""

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter

    def __getattr__(self, name: str) -> Any:
        return getattr(self._adapter, name)

    async def validate(
        self,
        identifier: str,
        credential: str | None = None,
        filters: Any = None,
        scope: Any = None,
        rules: Any = None,
    ) -> Any:
        chosen = filters or self._adapter.entry.default_filters
        return await self._adapter.validate(
            identifier, credential, software_filters(chosen), scope, rules or software_rules()
        )


def build(adapter_class: Callable[..., Any], sleeper: Sleeper | None = None) -> Any:
    """Create an adapter on a guarded client that resolves every host to a public address."""

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    client = GuardedHttpClient(guard=UrlGuard(resolver=resolve), user_agent="JobsRadar/test")
    sleeper = sleeper or Sleeper()
    return _SoftwareOwner(
        adapter_class(
            client,
            sleep=sleeper,
            limiter=RateLimiter(sleep=sleeper, clock=lambda: 0.0),
            clock=clock,
        )
    )


PORTUGAL = LocationScope(
    frozenset({"PT"}),
    include_worldwide=True,
    onsite_areas=(OnsiteArea("Lisbon", 38.72, -9.14, 40),),
)


def checkpoint(
    identifier: str,
    filters: JobBoardFilters | None = None,
    scope: LocationScope | None = PORTUGAL,
    *,
    default_areas: bool = True,
) -> SourceCheckpoint:
    """A checkpoint for a job board source; the scope is what the profile and intents give.

    Without filters the board's defaults apply, with every area of the software pack selected, as
    for an owner who has that pack on. ``default_areas=False`` leaves no filters at all.
    """
    return SourceCheckpoint(
        identifier=identifier,
        url=f"https://example.test/{identifier}",
        etag=None,
        rate_limit_per_minute=60,
        filters=software_filters(filters) if filters is not None or default_areas else None,
        scope=scope,
        rules=software_rules(),
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


def build_ats(
    adapter_class: Callable[..., Any], sleeper: Sleeper | None = None, **kwargs: Any
) -> Any:
    """Create a company-board adapter (no clock) on the same guarded client."""

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    client = GuardedHttpClient(guard=UrlGuard(resolver=resolve), user_agent="JobsRadar/test")
    sleeper = sleeper or Sleeper()
    return adapter_class(
        client, sleep=sleeper, limiter=RateLimiter(sleep=sleeper, clock=lambda: 0.0), **kwargs
    )


def ats_checkpoint(identifier: str, etag: str | None = None) -> SourceCheckpoint:
    """A checkpoint for a company-board source."""
    return SourceCheckpoint(
        identifier=identifier,
        url=f"https://example.test/{identifier}",
        etag=etag,
        rate_limit_per_minute=60,
        rules=software_rules(),
    )
