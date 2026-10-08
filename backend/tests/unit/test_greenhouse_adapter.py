"""The Greenhouse adapter against recorded synthetic payloads (ADR-015, ADR-035, document 13 section 5.1)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from jobs_radar.adapters.sources.base import RateLimiter, SourceCheckpoint, SourceError
from jobs_radar.adapters.sources.greenhouse import GreenhouseAdapter
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.core.url_guard import UrlGuard
from jobs_radar.domain.enums import SourceErrorClass

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "greenhouse"
BASE = "https://boards-api.greenhouse.io/v1/boards"
JOBS_URL = f"{BASE}/synthco/jobs"


def payload(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class Sleeper:
    """Records the waits the adapter asks for instead of sleeping."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def make_adapter(sleeper: Sleeper | None = None, **client_options: object) -> GreenhouseAdapter:
    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    client = GuardedHttpClient(
        guard=UrlGuard(resolver=resolve), user_agent="JobsRadar/test", **client_options
    )  # type: ignore[arg-type]
    sleeper = sleeper or Sleeper()
    return GreenhouseAdapter(
        client, sleep=sleeper, limiter=RateLimiter(sleep=sleeper, clock=lambda: 0.0)
    )


def checkpoint(etag: str | None = None) -> SourceCheckpoint:
    return SourceCheckpoint(identifier="synthco", url=JOBS_URL, etag=etag, rate_limit_per_minute=60)


# --- validation ------------------------------------------------------------------------------------


@respx.mock
async def test_validate_returns_the_company_name_and_posting_count() -> None:
    respx.get(f"{BASE}/synthco").respond(200, content=payload("board.json"))
    respx.get(JOBS_URL).respond(200, content=payload("jobs.json"))
    info = await make_adapter().validate("synthco")
    assert (info.name, info.postings_count) == ("Synthetic Co", 3)


@respx.mock
async def test_validate_an_unknown_board_is_not_found() -> None:
    respx.get(f"{BASE}/nope").respond(404)
    with pytest.raises(SourceError) as error:
        await make_adapter().validate("nope")
    assert error.value.error_class is SourceErrorClass.NOT_FOUND
    assert error.value.http_status == 404


@pytest.mark.parametrize("token", ["", "has space", "../etc", "a/b", "x" * 101, "ünï", "token?x=1"])
async def test_an_invalid_token_is_rejected_without_any_request(token: str) -> None:
    with respx.mock(assert_all_called=False) as router:
        with pytest.raises(SourceError) as error:
            await make_adapter().validate(token)
        assert router.calls.call_count == 0
    assert error.value.error_class is SourceErrorClass.CONFIGURATION


# --- collection --------------------------------------------------------------------------------------


@respx.mock
async def test_collect_maps_every_posting() -> None:
    respx.get(JOBS_URL, params={"content": "true"}).respond(
        200, content=payload("jobs.json"), headers={"ETag": 'W/"v1"'}
    )
    result = await make_adapter().collect(checkpoint())
    assert result.outcome == "modified"
    assert result.etag == 'W/"v1"'
    assert result.http_status == 200
    assert result.declared_total == 3
    first, second, third = result.postings

    assert first.external_job_id == "1001"
    assert first.title == "Senior AI Solutions Engineer"
    assert first.source_url == "https://job-boards.greenhouse.io/synthco/jobs/1001?gh_src=abc"
    assert first.locations == ("Remote - EU",)  # the office repeats the location: no duplicate
    assert first.posted_at == datetime(2026, 10, 1, 13, 30, tzinfo=UTC)  # 09:30 at UTC-4
    assert first.departments == ("Engineering",)
    assert first.language == "en"
    assert "Design & evaluate LLM-powered features" in first.description_text
    assert "tracker" not in first.description_text and "alert" not in first.description_text

    assert second.locations == (
        "Lisbon, Portugal",
        "Madrid, Spain",
    )  # office locations, no duplicates
    assert third.posted_at is None
    assert third.description_text == ""
    assert third.language is None


@respx.mock
async def test_collect_keeps_the_raw_payload_untouched() -> None:
    respx.get(JOBS_URL, params={"content": "true"}).respond(200, content=payload("jobs.json"))
    result = await make_adapter().collect(checkpoint())
    original = json.loads(payload("jobs.json"))["jobs"][0]
    assert result.postings[0].raw_payload == original
    assert result.postings[0].raw_payload["content"].startswith("&lt;div")  # still entity-escaped


@respx.mock
async def test_the_stored_etag_is_sent_and_a_304_means_nothing_changed() -> None:
    route = respx.get(JOBS_URL, params={"content": "true"}).respond(304, headers={"ETag": 'W/"v1"'})
    result = await make_adapter().collect(checkpoint(etag='W/"v1"'))
    assert route.calls.last.request.headers["if-none-match"] == 'W/"v1"'
    assert result.outcome == "not_modified"
    assert result.postings == ()
    assert result.etag == 'W/"v1"'


@respx.mock
async def test_a_304_keeps_the_previous_etag_when_the_header_is_absent() -> None:
    respx.get(JOBS_URL, params={"content": "true"}).respond(304)
    assert (await make_adapter().collect(checkpoint(etag='W/"old"'))).etag == 'W/"old"'


@respx.mock
async def test_an_empty_board_is_a_valid_result() -> None:
    respx.get(JOBS_URL, params={"content": "true"}).respond(200, content=payload("jobs_empty.json"))
    result = await make_adapter().collect(checkpoint())
    assert (result.outcome, result.postings, result.declared_total) == ("modified", (), 0)


@respx.mock
async def test_404_is_a_classified_error() -> None:
    respx.get(JOBS_URL, params={"content": "true"}).respond(404)
    with pytest.raises(SourceError) as error:
        await make_adapter().collect(checkpoint())
    assert error.value.error_class is SourceErrorClass.NOT_FOUND


@respx.mock
async def test_429_then_success_backs_off_using_retry_after() -> None:
    sleeper = Sleeper()
    route = respx.get(JOBS_URL, params={"content": "true"})
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(200, content=payload("jobs.json")),
    ]
    result = await make_adapter(sleeper).collect(checkpoint())
    assert len(result.postings) == 3
    assert 7 in sleeper.waits


@respx.mock
async def test_retry_after_is_capped() -> None:
    sleeper = Sleeper()
    route = respx.get(JOBS_URL, params={"content": "true"})
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "86400"}),
        httpx.Response(200, content=payload("jobs.json")),
    ]
    await make_adapter(sleeper).collect(checkpoint())
    assert max(sleeper.waits) <= 60


@respx.mock
async def test_persistent_429_gives_up_as_rate_limited_after_a_bounded_number_of_attempts() -> None:
    sleeper = Sleeper()
    route = respx.get(JOBS_URL, params={"content": "true"}).respond(429)
    with pytest.raises(SourceError) as error:
        await make_adapter(sleeper).collect(checkpoint())
    assert error.value.error_class is SourceErrorClass.RATE_LIMITED
    assert route.call_count == 3  # one try plus two retries: never an unbounded loop


@respx.mock
async def test_a_server_error_is_retried_then_succeeds() -> None:
    route = respx.get(JOBS_URL, params={"content": "true"})
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(200, content=payload("jobs_empty.json")),
    ]
    assert (await make_adapter().collect(checkpoint())).outcome == "modified"


@respx.mock
async def test_a_persistent_server_error_is_classified() -> None:
    respx.get(JOBS_URL, params={"content": "true"}).respond(500)
    with pytest.raises(SourceError) as error:
        await make_adapter().collect(checkpoint())
    assert error.value.error_class is SourceErrorClass.SERVER_ERROR
    assert error.value.http_status == 500


@respx.mock
@pytest.mark.parametrize(
    "body",
    [
        b"not json at all",
        b"[]",
        b'{"nothing": 1}',
        b'{"jobs": "x"}',
        b'{"jobs": [{"title": "no id"}]}',
    ],
)
async def test_malformed_payloads_are_invalid_not_crashes(body: bytes) -> None:
    respx.get(JOBS_URL, params={"content": "true"}).respond(200, content=body)
    with pytest.raises(SourceError) as error:
        await make_adapter().collect(checkpoint())
    assert error.value.error_class is SourceErrorClass.INVALID_PAYLOAD


@respx.mock
async def test_an_oversized_answer_is_too_large() -> None:
    respx.get(JOBS_URL, params={"content": "true"}).respond(200, content=b"x" * 5000)
    with pytest.raises(SourceError) as error:
        await make_adapter(max_bytes=1000).collect(checkpoint())
    assert error.value.error_class is SourceErrorClass.TOO_LARGE


@respx.mock
async def test_a_timeout_is_classified() -> None:
    respx.get(JOBS_URL, params={"content": "true"}).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(SourceError) as error:
        await make_adapter().collect(checkpoint())
    assert error.value.error_class is SourceErrorClass.TIMEOUT


@respx.mock
async def test_a_network_failure_is_classified() -> None:
    respx.get(JOBS_URL, params={"content": "true"}).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(SourceError) as error:
        await make_adapter().collect(checkpoint())
    assert error.value.error_class is SourceErrorClass.NETWORK_ERROR


# --- rate limiter ----------------------------------------------------------------------------------------


async def test_the_rate_limiter_spaces_requests_per_key() -> None:
    now = [0.0]
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(sleep=sleep, clock=lambda: now[0])
    await limiter.wait("a", per_minute=6)  # first request goes straight through
    await limiter.wait("a", per_minute=6)  # 10 s minimum interval
    await limiter.wait("b", per_minute=6)  # another key is independent
    assert waits == [10.0]
