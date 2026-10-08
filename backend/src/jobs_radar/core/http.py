"""The one outbound HTTP client used by every adapter (ADR-035).

It enforces the URL policy on the first request and on every redirect, bounds connection and total
time, aborts bodies over a size limit, identifies the application in the User-Agent, and turns
every failure into a :class:`FetchError` with a stable ``error_class`` and a message that does not
leak addresses or internals. No adapter creates its own HTTP client.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from jobs_radar import __version__
from jobs_radar.core.url_guard import BlockedUrlError, UrlGuard

DEFAULT_MAX_BYTES = 25 * 1024 * 1024
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class FetchError(Exception):
    """A request failed. ``error_class`` is a stable machine-readable reason."""

    def __init__(self, error_class: str, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True)
class HttpResponse:
    """A completed response. Header names are lower-cased."""

    status: int
    headers: Mapping[str, str]
    body: bytes
    url: str


class GuardedHttpClient:
    """Guarded, bounded ``GET`` requests."""

    def __init__(
        self,
        *,
        guard: UrlGuard,
        user_agent: str,
        connect_timeout: float = 5.0,
        total_timeout: float = 30.0,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_redirects: int = 3,
    ) -> None:
        self._guard = guard
        self._user_agent = user_agent
        self._total_timeout = total_timeout
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects
        self._timeout = httpx.Timeout(total_timeout, connect=connect_timeout)
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            # Redirects are followed by hand so that every hop passes the URL guard.
            self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=False)
        return self._client

    async def aclose(self) -> None:
        """Release the underlying connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> HttpResponse:
        """Request ``url`` and return the final response (redirects followed within the limit).

        Raises:
            FetchError: blocked URL, too many redirects, timeout, network failure or oversized body.
        """
        request_headers = {"User-Agent": self._user_agent, **(headers or {})}
        current = url
        for _ in range(self._max_redirects + 1):
            try:
                await self._guard.check(current)
            except BlockedUrlError as exc:
                raise FetchError("blocked_url", str(exc)) from exc
            response = await self._request_once(current, request_headers)
            location = response.headers.get("location")
            if response.status in _REDIRECT_STATUSES and location:
                current = urljoin(current, location)
                continue
            return response
        msg = "The source redirected too many times."
        raise FetchError("too_many_redirects", msg)

    async def _request_once(self, url: str, headers: Mapping[str, str]) -> HttpResponse:
        try:
            async with asyncio.timeout(self._total_timeout):
                async with self._http().stream("GET", url, headers=dict(headers)) as response:
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_bytes:
                            msg = "The source's answer is larger than the allowed limit."
                            raise FetchError("too_large", msg)
                    return HttpResponse(
                        status=response.status_code,
                        headers={key.lower(): value for key, value in response.headers.items()},
                        body=bytes(body),
                        url=url,
                    )
        except (TimeoutError, httpx.TimeoutException) as exc:
            msg = "The source did not answer in time."
            raise FetchError("timeout", msg) from exc
        except httpx.HTTPError as exc:
            # Details (addresses, ports) are deliberately not copied into the message.
            msg = "Could not connect to the source."
            raise FetchError("network_error", msg) from exc


def build_http_client(*, guard: UrlGuard | None = None) -> GuardedHttpClient:
    """Create the application's HTTP client with the production policy."""
    return GuardedHttpClient(
        guard=guard or UrlGuard(),
        user_agent=f"JobsRadar/{__version__} (personal job-market radar)",
    )
