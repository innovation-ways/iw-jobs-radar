"""The only HTTP code of the MCP server: a small client of the Jobs Radar REST API (ADR-078).

It is deliberately not the adapters' ``GuardedHttpClient`` (ADR-035): that one blocks private
addresses, and this one talks to the owner's own API on loopback or the LAN. What it does instead:
one configured base URL, a fixed allow-list of method + path templates (an agent can never choose
a path or a URL), integer-only path parameters, no redirects, bounded time and size, and the API's
error envelope turned into :class:`ApiError`. Raw response bodies are never echoed.
"""

from collections.abc import Mapping, Sequence
from typing import Any

import httpx

API_PREFIX = "/api/v1"
DEFAULT_MAX_BYTES = 4 * 1024 * 1024

# Method + path template. Keep in step with backend/openapi.json (a unit test checks it).
READ_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/pipeline/status"),
        ("GET", "/widget/summary"),
        ("GET", "/inbox"),
        ("GET", "/inbox/{job_inbox_item_id}"),
        ("GET", "/digests/daily"),
        ("GET", "/profiles"),
        ("GET", "/profiles/{career_profile_id}/intents"),
        ("GET", "/sources"),
        ("GET", "/collection-runs"),
        ("GET", "/companies"),
        ("GET", "/companies/{company_id}"),
        ("GET", "/trends"),
    }
)
WRITE_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/inbox/{job_inbox_item_id}/actions"),
        ("POST", "/collection-runs"),
        ("POST", "/jobs/{job_posting_id}/summary"),
    }
)
ALLOWED_ROUTES = READ_ROUTES | WRITE_ROUTES

_UNREACHABLE = (
    "Jobs Radar is not reachable at the configured address. Start it with `make up` "
    "(or ./jobs-radar.sh --quick-start) and check JOBS_RADAR_MCP_API_URL."
)

QueryValue = str | int | float | bool | Sequence[str] | None


class ApiError(Exception):
    """A request failed; ``code`` is stable and ``message`` is safe to show an agent."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        details: Any = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status = status
        self.details = details
        self.request_id = request_id


def _query_items(
    params: Mapping[str, QueryValue],
) -> list[tuple[str, str | int | float | bool | None]]:
    items: list[tuple[str, str | int | float | bool | None]] = []
    for name, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            items.append((name, "true" if value else "false"))
        elif isinstance(value, str | int | float):
            items.append((name, str(value)))
        else:
            items.extend((name, str(entry)) for entry in value)
    return items


def _positive_int(name: str, value: object) -> int:
    # bool is an int subclass; True must not become id 1.
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        msg = f"path parameter {name} must be a positive integer"
        raise ValueError(msg)
    return value


class ApiClient:
    """Call the API's allow-listed routes and return the decoded JSON."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float,
        max_bytes: int = DEFAULT_MAX_BYTES,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._max_bytes = max_bytes
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
            follow_redirects=False,
            transport=transport,
            headers={"accept": "application/json", "user-agent": "jobs-radar-mcp"},
        )

    async def aclose(self) -> None:
        """Release the connection pool."""
        await self._http.aclose()

    async def get(
        self,
        template: str,
        *,
        path: Mapping[str, int] | None = None,
        params: Mapping[str, QueryValue] | None = None,
    ) -> Any:
        """``GET`` an allow-listed route."""
        return await self._request("GET", template, path=path, params=params, body=None)

    async def post(
        self,
        template: str,
        *,
        path: Mapping[str, int] | None = None,
        params: Mapping[str, QueryValue] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> Any:
        """``POST`` JSON to an allow-listed route."""
        return await self._request("POST", template, path=path, params=params, body=json)

    async def _request(
        self,
        method: str,
        template: str,
        *,
        path: Mapping[str, int] | None,
        params: Mapping[str, QueryValue] | None,
        body: Mapping[str, Any] | None,
    ) -> Any:
        if (method, template) not in ALLOWED_ROUTES:
            msg = f"{method} {template!r} is not an allowed route"
            raise ValueError(msg)
        url = template
        for name, value in (path or {}).items():
            url = url.replace("{" + name + "}", str(_positive_int(name, value)))
        if "{" in url:
            msg = f"missing path parameter for {template!r}"
            raise ValueError(msg)
        try:
            async with self._http.stream(
                method,
                API_PREFIX + url,
                params=httpx.QueryParams(_query_items(params or {})),
                json=None if body is None else dict(body),
            ) as response:
                payload = await self._read_body(response)
                status = response.status_code
        except httpx.TimeoutException as error:
            raise ApiError("api_timeout", "Jobs Radar did not answer in time.") from error
        except httpx.TransportError as error:
            raise ApiError("api_unreachable", _UNREACHABLE) from error
        return self._decode(status, payload)

    async def _read_body(self, response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > self._max_bytes:
                raise ApiError(
                    "response_too_large",
                    "The answer is larger than the limit; use filters or a smaller page.",
                    status=response.status_code,
                )
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _decode(status: int, payload: bytes) -> Any:
        if 300 <= status < 400:
            raise ApiError(
                "unexpected_redirect", "The API answered with a redirect.", status=status
            )
        try:
            data = httpx.Response(status, content=payload).json() if payload else None
        except ValueError:
            data = None
            if status < 400:
                raise ApiError(
                    "invalid_response", "The API did not answer with JSON.", status=status
                ) from None
        if status >= 400:
            envelope = data.get("error") if isinstance(data, dict) else None
            if isinstance(envelope, dict) and isinstance(envelope.get("code"), str):
                raise ApiError(
                    envelope["code"],
                    str(envelope.get("message", "The API refused the request.")),
                    status=status,
                    details=envelope.get("details"),
                    request_id=envelope.get("request_id"),
                )
            raise ApiError("api_error", f"The API answered with status {status}.", status=status)
        return data
