"""The shared outbound HTTP client: timeouts, size limit, guarded redirects, safe errors (ADR-035)."""

import httpx
import pytest
import respx

from jobs_radar.core.http import FetchError, GuardedHttpClient
from jobs_radar.core.url_guard import UrlGuard

URL = "https://boards.example.test/v1/boards/x/jobs"


def make_client(**options: object) -> GuardedHttpClient:
    async def resolve(host: str) -> list[str]:
        return {
            "boards.example.test": ["93.184.216.34"],
            "other.example.test": ["93.184.216.35"],
            "evil.example.test": ["10.0.0.9"],
        }[host]

    return GuardedHttpClient(
        guard=UrlGuard(resolver=resolve), user_agent="JobsRadar/test", **options
    )  # type: ignore[arg-type]


@respx.mock
async def test_a_successful_get_returns_status_headers_and_body() -> None:
    respx.get(URL).respond(200, json={"jobs": []}, headers={"ETag": 'W/"abc"'})
    response = await make_client().get(URL)
    assert response.status == 200
    assert response.headers["etag"] == 'W/"abc"'
    assert response.body == b'{"jobs":[]}'


@respx.mock
async def test_the_user_agent_and_extra_headers_are_sent() -> None:
    route = respx.get(URL).respond(200, content=b"{}")
    await make_client().get(URL, headers={"If-None-Match": 'W/"abc"'})
    request = route.calls.last.request
    assert request.headers["user-agent"] == "JobsRadar/test"
    assert request.headers["if-none-match"] == 'W/"abc"'


@respx.mock
async def test_a_not_modified_answer_is_returned_not_raised() -> None:
    respx.get(URL).respond(304)
    assert (await make_client().get(URL)).status == 304


@respx.mock
async def test_client_and_server_errors_are_returned_for_the_caller_to_classify() -> None:
    respx.get(URL).respond(404)
    assert (await make_client().get(URL)).status == 404


@respx.mock
async def test_a_body_over_the_limit_is_aborted() -> None:
    respx.get(URL).respond(200, content=b"x" * 5000)
    with pytest.raises(FetchError) as error:
        await make_client(max_bytes=1000).get(URL)
    assert error.value.error_class == "too_large"


@respx.mock
async def test_a_redirect_to_an_allowed_host_is_followed() -> None:
    respx.get(URL).respond(302, headers={"Location": "https://other.example.test/final"})
    respx.get("https://other.example.test/final").respond(200, content=b"ok")
    response = await make_client().get(URL)
    assert (response.status, response.body) == (200, b"ok")


@respx.mock
async def test_a_redirect_into_a_private_address_is_blocked() -> None:
    respx.get(URL).respond(302, headers={"Location": "https://evil.example.test/x"})
    with pytest.raises(FetchError) as error:
        await make_client().get(URL)
    assert error.value.error_class == "blocked_url"


@respx.mock
async def test_too_many_redirects_fail() -> None:
    respx.get(URL).respond(302, headers={"Location": URL})
    with pytest.raises(FetchError) as error:
        await make_client(max_redirects=2).get(URL)
    assert error.value.error_class == "too_many_redirects"


@respx.mock
async def test_a_timeout_is_classified() -> None:
    respx.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(FetchError) as error:
        await make_client().get(URL)
    assert error.value.error_class == "timeout"


@respx.mock
async def test_a_connection_failure_is_classified_without_leaking_details() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectError("connection refused to 10.1.2.3:443"))
    with pytest.raises(FetchError) as error:
        await make_client().get(URL)
    assert error.value.error_class == "network_error"
    assert "10.1.2.3" not in error.value.message


async def test_a_blocked_url_never_reaches_the_network() -> None:
    with pytest.raises(FetchError) as error:
        await make_client().get(
            "https://evil.example.test/x"
        )  # resolves to a private address; no respx mock needed
    assert error.value.error_class == "blocked_url"
