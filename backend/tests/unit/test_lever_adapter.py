"""The Lever adapter against recorded synthetic payloads (ADR-050, research R-00169)."""

from datetime import UTC, datetime

import pytest
import respx
from tests.job_board_support import Sleeper, ats_checkpoint, build_ats, payload

from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.adapters.sources.lever import LeverAdapter
from jobs_radar.domain.enums import SourceErrorClass, SourceType

URL = "https://api.lever.co/v0/postings/synthco"


@respx.mock
async def test_collect_maps_every_posting() -> None:
    respx.get(URL, params={"mode": "json"}).respond(
        200, content=payload("lever", "postings.json"), headers={"ETag": 'W/"v1"'}
    )
    result = await build_ats(LeverAdapter).collect(ats_checkpoint("synthco"))
    assert result.outcome == "modified"
    assert result.etag == 'W/"v1"'
    assert result.declared_total == 3
    first, second, third = result.postings

    assert first.external_job_id == "00000000-0000-0000-0000-000000000001"
    assert first.title == "Senior Backend Engineer"
    assert first.source_url == "https://jobs.lever.co/synthco/00000000-0000-0000-0000-000000000001"
    assert first.apply_url.endswith("/apply")
    assert first.locations == ("Lisbon", "Madrid")
    assert first.departments == ("Engineering", "Platform")
    assert first.posted_at == datetime.fromtimestamp(1790000000, UTC)
    assert first.company_name is None  # a company board has its own company
    for text in (
        "Build synthetic things.",
        "What you will do",
        "Design services",
        "equal opportunity",
    ):
        assert text in first.description_text
    assert "<" not in first.description_text

    assert second.locations == ("Remote - EU",)  # remote workplace, already says so
    assert third.posted_at is None
    assert third.description_text == ""


@respx.mock
async def test_a_remote_workplace_without_a_remote_place_is_marked_remote() -> None:
    body = b'[{"id": "x1", "text": "Engineer", "categories": {"location": "Lisbon"}, "workplaceType": "remote", "hostedUrl": "https://jobs.lever.co/synthco/x1", "applyUrl": "https://jobs.lever.co/synthco/x1/apply"}]'
    respx.get(URL, params={"mode": "json"}).respond(200, content=body)
    result = await build_ats(LeverAdapter).collect(ats_checkpoint("synthco"))
    assert result.postings[0].locations == ("Lisbon", "Remote")


@respx.mock
async def test_the_stored_etag_is_sent_and_a_304_means_nothing_changed() -> None:
    route = respx.get(URL, params={"mode": "json"}).respond(304, headers={"ETag": 'W/"v1"'})
    result = await build_ats(LeverAdapter).collect(ats_checkpoint("synthco", etag='W/"v1"'))
    assert route.calls.last.request.headers["if-none-match"] == 'W/"v1"'
    assert (result.outcome, result.postings) == ("not_modified", ())


@respx.mock
async def test_validate_names_the_company_from_its_identifier_and_counts_postings() -> None:
    respx.get(URL, params={"mode": "json"}).respond(200, content=payload("lever", "postings.json"))
    info = await build_ats(LeverAdapter).validate("synthco")
    assert (info.name, info.postings_count) == ("Synthco", 3)
    respx.get("https://api.lever.co/v0/postings/synth-co", params={"mode": "json"}).respond(
        200, content=b"[]"
    )
    assert (await build_ats(LeverAdapter).validate("synth-co")).name == "Synth Co"


@respx.mock
async def test_an_unknown_company_is_not_found() -> None:
    respx.get("https://api.lever.co/v0/postings/nope", params={"mode": "json"}).respond(
        404, json={"ok": False, "error": "Document not found"}
    )
    with pytest.raises(SourceError) as error:
        await build_ats(LeverAdapter).validate("nope")
    assert error.value.error_class is SourceErrorClass.NOT_FOUND


@pytest.mark.parametrize("token", ["", "has space", "../etc", "a/b", "x" * 101, "token?x=1"])
async def test_an_invalid_identifier_is_rejected_without_any_request(token: str) -> None:
    with respx.mock(assert_all_called=False) as router:
        with pytest.raises(SourceError) as error:
            await build_ats(LeverAdapter).validate(token)
        assert router.calls.call_count == 0
    assert error.value.error_class is SourceErrorClass.CONFIGURATION


@respx.mock
@pytest.mark.parametrize("body", [b"nope", b'{"ok": false}', b'"text"'])
async def test_an_answer_that_is_not_a_list_is_invalid(body: bytes) -> None:
    respx.get(URL, params={"mode": "json"}).respond(200, content=body)
    with pytest.raises(SourceError) as error:
        await build_ats(LeverAdapter).collect(ats_checkpoint("synthco"))
    assert error.value.error_class is SourceErrorClass.INVALID_PAYLOAD


@respx.mock
async def test_a_malformed_posting_is_an_invalid_payload() -> None:
    respx.get(URL, params={"mode": "json"}).respond(200, content=b'[{"id": "1"}]')
    with pytest.raises(SourceError) as error:
        await build_ats(LeverAdapter).collect(ats_checkpoint("synthco"))
    assert error.value.error_class is SourceErrorClass.INVALID_PAYLOAD


@respx.mock
async def test_rate_limiting_is_retried_then_classified() -> None:
    route = respx.get(URL, params={"mode": "json"}).respond(429)
    sleeper = Sleeper()
    with pytest.raises(SourceError) as error:
        await build_ats(LeverAdapter, sleeper).collect(ats_checkpoint("synthco"))
    assert error.value.error_class is SourceErrorClass.RATE_LIMITED
    assert route.call_count == 3


def test_type_and_endpoint() -> None:
    adapter = build_ats(LeverAdapter)
    assert adapter.source_type is SourceType.LEVER
    assert adapter.endpoint("synthco") == URL
