"""Shared pieces of the public-dataset adapters (ADR-025, ADR-035, research R-00171).

Every adapter goes through :class:`PublicApi`: the one guarded HTTP client, a minimum interval
between requests to the same dataset, JSON parsing and classified errors. Errors never include the
company name or the answer. Each fact an adapter returns carries its source, address and licence.
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from jobs_radar.core.http import FetchError, GuardedHttpClient


class EnrichmentError(Exception):
    """A dataset could not be read. ``error_class`` is stable; the message is generic."""

    def __init__(self, error_class: str, message: str) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.message = message


@dataclass(frozen=True)
class FactValue:
    """A fact value with where it came from and under which licence."""

    value: Any
    source_name: str
    source_url: str
    licence: str


@dataclass(frozen=True)
class EntityCandidate:
    """An entity of a dataset that may be the company."""

    source_name: str
    external_id: str
    label: str
    description: str | None
    website: str | None
    facts: dict[str, FactValue] = field(default_factory=dict)
    wikipedia_title: str | None = None
    github_login: str | None = None


class PublicApi:
    """Guarded, spaced-out JSON reads from one dataset."""

    def __init__(
        self,
        client: GuardedHttpClient,
        *,
        min_interval: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._min_interval = min_interval
        self._sleep = sleep
        self._clock = clock
        self._next_free: float | None = None

    async def get_json(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        *,
        headers: Mapping[str, str] | None = None,
        allow_not_found: bool = False,
    ) -> Any:
        """GET ``url`` and return the parsed JSON (``None`` for a 404 when allowed)."""
        now = self._clock()
        wait = 0.0 if self._next_free is None else max(0.0, self._next_free - now)
        if wait:
            await self._sleep(wait)
        self._next_free = now + wait + self._min_interval
        full = f"{url}?{urlencode(params)}" if params else url
        try:
            response = await self._client.get(full, headers=headers)
        except FetchError as exc:
            raise EnrichmentError(
                "blocked_url" if exc.error_class == "blocked_url" else "unavailable",
                "The dataset could not be reached.",
            ) from exc
        if response.status == 404 and allow_not_found:
            return None
        if response.status in {403, 429}:
            limited = response.headers.get("x-ratelimit-remaining") == "0" or response.status == 429
            raise EnrichmentError(
                "rate_limited" if limited else "http_error", "The dataset refused the request."
            )
        if response.status != 200:
            raise EnrichmentError("http_error", "The dataset reported an error.")
        try:
            return json.loads(response.body)
        except ValueError as exc:
            raise EnrichmentError(
                "invalid_response", "The dataset answered with unusable data."
            ) from exc
