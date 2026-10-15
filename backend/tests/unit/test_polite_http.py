"""The polite getter retries transport failures as well as 429 and 5xx (ADR-042.5)."""

import httpx
import pytest
import respx
from tests.job_board_support import Sleeper

from jobs_radar.adapters.sources.base import RateLimiter, SourceError
from jobs_radar.adapters.sources.polite_http import MAX_ATTEMPTS, PoliteGetter
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.core.url_guard import UrlGuard
from jobs_radar.domain.enums import SourceErrorClass

URL = "https://source.example/page"


def getter(sleeper: Sleeper) -> PoliteGetter:
    """A getter on a client that resolves every host to a public address."""

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    client = GuardedHttpClient(guard=UrlGuard(resolver=resolve), user_agent="JobsRadar/test")
    return PoliteGetter(
        client, sleep=sleeper, limiter=RateLimiter(sleep=sleeper, clock=lambda: 0.0)
    )


@respx.mock
@pytest.mark.parametrize("failure", [httpx.ConnectError("down"), httpx.ConnectTimeout("slow")])
async def test_a_transport_failure_is_retried_and_the_next_attempt_can_succeed(
    failure: Exception,
) -> None:
    route = respx.get(URL).mock(side_effect=[failure, httpx.Response(200, content=b"ok")])
    response = await getter(Sleeper()).get(URL, {}, "key", per_minute=60)
    assert response.body == b"ok"
    assert route.call_count == 2


@respx.mock
async def test_a_transport_failure_that_persists_fails_after_the_attempt_limit() -> None:
    route = respx.get(URL).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(SourceError) as error:
        await getter(Sleeper()).get(URL, {}, "key", per_minute=60)
    assert error.value.error_class is SourceErrorClass.NETWORK_ERROR
    assert route.call_count == MAX_ATTEMPTS


@respx.mock
async def test_an_address_the_guard_blocks_is_not_retried() -> None:
    async def resolve(host: str) -> list[str]:
        return ["169.254.169.254"]

    client = GuardedHttpClient(guard=UrlGuard(resolver=resolve), user_agent="JobsRadar/test")
    sleeper = Sleeper()
    polite = PoliteGetter(
        client, sleep=sleeper, limiter=RateLimiter(sleep=sleeper, clock=lambda: 0.0)
    )
    route = respx.get(URL).mock(return_value=httpx.Response(200))
    with pytest.raises(SourceError) as error:
        await polite.get(URL, {}, "key", per_minute=60)
    assert error.value.error_class is SourceErrorClass.BLOCKED_URL
    assert route.call_count == 0
