"""Rate-limited GET with bounded retries, shared by the source adapters (ADR-042.5, ADR-049.8).

A request is spaced by the source's rate limit, retried at most three times in total on 429 and 5xx
(honouring ``Retry-After``, capped), and every failure becomes a classified :class:`SourceError`
whose message never contains an address or a payload.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from jobs_radar.adapters.sources.base import RateLimiter, SourceError, source_error_from_fetch
from jobs_radar.core.http import FetchError, GuardedHttpClient, HttpResponse
from jobs_radar.domain.enums import SourceErrorClass

MAX_ATTEMPTS = 3
MAX_BACKOFF_SECONDS = 60.0

Sleep = Callable[[float], Awaitable[None]]


class PoliteGetter:
    """GET requests to one kind of source with spacing, retries and error classification."""

    def __init__(
        self,
        client: GuardedHttpClient,
        *,
        sleep: Any = asyncio.sleep,
        limiter: RateLimiter | None = None,
        not_found_message: str = "The source was not found.",
        auth_statuses: frozenset[int] = frozenset(),
    ) -> None:
        self._client = client
        self._sleep: Sleep = sleep
        self._limiter = limiter or RateLimiter()
        self._not_found_message = not_found_message
        # Statuses that mean "the credential was refused"; never retried.
        self._auth_statuses = auth_statuses

    async def get(
        self, url: str, headers: dict[str, str], key: str, *, per_minute: int
    ) -> HttpResponse:
        """GET ``url``; 200 and 304 are returned, everything else raises :class:`SourceError`."""
        last_class = SourceErrorClass.UNKNOWN
        last_status = 0
        for attempt in range(1, MAX_ATTEMPTS + 1):
            await self._limiter.wait(key, per_minute)
            try:
                response = await self._client.get(url, headers=headers)
            except FetchError as exc:
                raise source_error_from_fetch(exc) from exc
            status = response.status
            if status in (200, 304):
                return response
            if status in self._auth_statuses:
                msg = "The source refused the credential."
                raise SourceError(SourceErrorClass.AUTHENTICATION, msg, http_status=status)
            if status == 404:
                raise SourceError(
                    SourceErrorClass.NOT_FOUND, self._not_found_message, http_status=status
                )
            if status == 429 or status >= 500:
                last_class = (
                    SourceErrorClass.RATE_LIMITED
                    if status == 429
                    else SourceErrorClass.SERVER_ERROR
                )
                last_status = status
                if attempt < MAX_ATTEMPTS:
                    await self._sleep(self._backoff(response, attempt))
                continue
            msg = f"The source answered with an unexpected status ({status})."
            raise SourceError(SourceErrorClass.HTTP_ERROR, msg, http_status=status)
        msg = (
            "The source is limiting requests; try again later."
            if last_class is SourceErrorClass.RATE_LIMITED
            else "The source reported an error; try again later."
        )
        raise SourceError(last_class, msg, http_status=last_status)

    @staticmethod
    def _backoff(response: HttpResponse, attempt: int) -> float:
        """Seconds to wait: ``Retry-After`` if the source sent one, else 2, 4, ... (capped)."""
        header = response.headers.get("retry-after", "")
        wait = float(header) if header.isdigit() else float(2**attempt)
        return min(wait, MAX_BACKOFF_SECONDS)
