"""The MCP server's only HTTP code: allow-list, limits, error mapping (ADR-078 point 9)."""

import json
from collections.abc import Callable

import httpx
import pytest

from jobs_radar.mcp_server.api_client import ALLOWED_ROUTES, ApiClient, ApiError

BASE = "http://127.0.0.1:8100"


def _client(
    handler: Callable[[httpx.Request], httpx.Response], *, max_bytes: int = 1_000_000
) -> ApiClient:
    return ApiClient(BASE, timeout=5.0, max_bytes=max_bytes, transport=httpx.MockTransport(handler))


def _json(body: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body)


async def test_get_sends_query_without_nones_and_with_repeated_lists() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _json({"ok": True})

    client = _client(handler)
    result = await client.get(
        "/inbox",
        params={
            "state": "unread",
            "q": None,
            "shortlisted": True,
            "engagement": ["freelance", "unknown"],
            "limit": 5,
        },
    )
    assert result == {"ok": True}
    url = seen[0].url
    assert url.path == "/api/v1/inbox"
    assert url.params.get_list("engagement") == ["freelance", "unknown"]
    assert url.params["shortlisted"] == "true"
    assert url.params["limit"] == "5"
    assert "q" not in url.params
    await client.aclose()


async def test_path_parameters_are_integers_and_substituted() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return _json({})

    client = _client(handler)
    await client.get("/inbox/{job_inbox_item_id}", path={"job_inbox_item_id": 42})
    assert seen == ["/api/v1/inbox/42"]
    for bad in ("42/../../settings/ai", 0, -3, True):
        with pytest.raises(ValueError, match="positive integer"):
            await client.get("/inbox/{job_inbox_item_id}", path={"job_inbox_item_id": bad})  # type: ignore[dict-item]
    assert seen == ["/api/v1/inbox/42"]


async def test_route_outside_the_allow_list_is_refused_before_any_request() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _json({})

    client = _client(handler)
    for path in ("/settings/ai", "/documents", "/inbox/../settings/ai", "http://evil.test/x"):
        with pytest.raises(ValueError, match="not an allowed route"):
            await client.get(path)
    with pytest.raises(ValueError, match="not an allowed route"):
        await client.post("/inbox", json={})  # GET-only route
    with pytest.raises(ValueError, match="not an allowed route"):
        await client.get("/inbox/{job_inbox_item_id}/actions", path={"job_inbox_item_id": 1})
    assert calls == 0


async def test_post_sends_json_body() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return _json({"queued": True}, 202)

    client = _client(handler)
    assert await client.post("/collection-runs", json={"scope": "all"}) == {"queued": True}
    assert seen == [{"scope": "all"}]


async def test_api_error_envelope_is_mapped() -> None:
    body = {
        "error": {
            "code": "version_conflict",
            "message": "The item changed.",
            "details": {"current_version": 4},
            "request_id": "req-1",
        }
    }
    client = _client(lambda _r: _json(body, 409))
    with pytest.raises(ApiError) as caught:
        await client.get("/inbox")
    error = caught.value
    assert (error.code, error.status, error.request_id) == ("version_conflict", 409, "req-1")
    assert error.details == {"current_version": 4}
    assert "The item changed." in str(error)


@pytest.mark.parametrize("status", [404, 422, 500, 503])
async def test_non_envelope_errors_get_a_generic_code(status: int) -> None:
    client = _client(lambda _r: httpx.Response(status, text="<html>boom</html>"))
    with pytest.raises(ApiError) as caught:
        await client.get("/inbox")
    assert caught.value.status == status
    assert "boom" not in str(caught.value)  # raw bodies are never echoed


async def test_connection_error_says_the_api_is_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = _client(handler)
    with pytest.raises(ApiError) as caught:
        await client.get("/inbox")
    assert caught.value.code == "api_unreachable"
    assert "make up" in str(caught.value)
    assert caught.value.status is None


async def test_timeout_is_mapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = _client(handler)
    with pytest.raises(ApiError) as caught:
        await client.get("/inbox")
    assert caught.value.code == "api_timeout"


async def test_redirects_are_not_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(307, headers={"location": "http://evil.test/"})

    client = _client(handler)
    with pytest.raises(ApiError) as caught:
        await client.get("/inbox")
    assert caught.value.code == "unexpected_redirect"


async def test_oversize_body_is_refused() -> None:
    client = _client(
        lambda _r: httpx.Response(200, content=b'{"x":"' + b"a" * 5000 + b'"}'), max_bytes=1000
    )
    with pytest.raises(ApiError) as caught:
        await client.get("/inbox")
    assert caught.value.code == "response_too_large"


async def test_non_json_success_is_an_error() -> None:
    client = _client(lambda _r: httpx.Response(200, text="not json"))
    with pytest.raises(ApiError) as caught:
        await client.get("/inbox")
    assert caught.value.code == "invalid_response"


def test_allow_list_covers_reads_and_exactly_three_writes() -> None:
    writes = {route for route in ALLOWED_ROUTES if route[0] != "GET"}
    assert writes == {
        ("POST", "/inbox/{job_inbox_item_id}/actions"),
        ("POST", "/collection-runs"),
        ("POST", "/jobs/{job_posting_id}/summary"),
    }
    forbidden = ("settings", "documents", "credential", "proposals", "delete")
    assert not [r for r in ALLOWED_ROUTES if any(word in r[1] for word in forbidden)]
