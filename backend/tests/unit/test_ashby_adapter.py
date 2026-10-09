"""The Ashby adapter against recorded synthetic payloads (ADR-050, research R-00169)."""

from datetime import UTC, datetime

import pytest
import respx
from tests.job_board_support import Sleeper, ats_checkpoint, build_ats, payload

from jobs_radar.adapters.sources.ashby import AshbyAdapter
from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.domain.enums import SourceErrorClass, SourceType

URL = "https://api.ashbyhq.com/posting-api/job-board/synthco"
PARAMS = {"includeCompensation": "true"}


@respx.mock
async def test_collect_maps_the_listed_postings_only() -> None:
    respx.get(URL, params=PARAMS).respond(
        200, content=payload("ashby", "board.json"), headers={"ETag": 'W/"job-board:1"'}
    )
    result = await build_ats(AshbyAdapter).collect(ats_checkpoint("synthco"))
    assert result.etag == 'W/"job-board:1"'
    assert result.declared_total == 2  # the unlisted role is not counted
    first, second = result.postings
    assert first.external_job_id == "aaaaaaaa-0000-0000-0000-000000000001"
    assert first.title == "Staff Infrastructure Engineer"
    assert (
        first.source_url == "https://jobs.ashbyhq.com/synthco/aaaaaaaa-0000-0000-0000-000000000001"
    )
    assert first.apply_url.endswith("/application")
    assert first.locations == ("Remote - Portugal", "Spain")
    assert first.departments == ("Engineering", "Core")
    assert first.posted_at == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    assert "Run synthetic infrastructure." in first.description_text
    assert "<" not in first.description_text
    assert (
        "€80K \N{EN DASH} €110K" in first.description_text
    )  # compensation, when the company shows it
    assert second.locations == ("Lisbon",)
    assert "Compensation" not in second.description_text


@respx.mock
async def test_a_remote_flag_without_a_remote_place_is_marked_remote() -> None:
    body = b'{"jobs": [{"id": "j1", "title": "Engineer", "location": "Lisbon", "isRemote": true, "isListed": true, "jobUrl": "https://jobs.ashbyhq.com/synthco/j1", "applyUrl": "https://jobs.ashbyhq.com/synthco/j1/application", "descriptionPlain": "x"}]}'
    respx.get(URL, params=PARAMS).respond(200, content=body)
    result = await build_ats(AshbyAdapter).collect(ats_checkpoint("synthco"))
    assert result.postings[0].locations == ("Lisbon", "Remote")


@respx.mock
async def test_the_stored_etag_is_sent_and_a_304_means_nothing_changed() -> None:
    route = respx.get(URL, params=PARAMS).respond(304)
    result = await build_ats(AshbyAdapter).collect(
        ats_checkpoint("synthco", etag='W/"job-board:1"')
    )
    assert route.calls.last.request.headers["if-none-match"] == 'W/"job-board:1"'
    assert result.outcome == "not_modified"
    assert result.etag == 'W/"job-board:1"'


@respx.mock
async def test_validate_names_the_company_and_counts_listed_postings() -> None:
    respx.get(URL, params=PARAMS).respond(200, content=payload("ashby", "board.json"))
    info = await build_ats(AshbyAdapter).validate("synthco")
    assert (info.name, info.postings_count) == ("Synthco", 2)


@respx.mock
async def test_an_unknown_board_is_not_found() -> None:
    respx.get("https://api.ashbyhq.com/posting-api/job-board/nope", params=PARAMS).respond(404)
    with pytest.raises(SourceError) as error:
        await build_ats(AshbyAdapter).validate("nope")
    assert error.value.error_class is SourceErrorClass.NOT_FOUND


@pytest.mark.parametrize("token", ["", "has space", "../etc", "a/b", "x" * 101, "token?x=1"])
async def test_an_invalid_identifier_is_rejected_without_any_request(token: str) -> None:
    with respx.mock(assert_all_called=False) as router:
        with pytest.raises(SourceError) as error:
            await build_ats(AshbyAdapter).validate(token)
        assert router.calls.call_count == 0
    assert error.value.error_class is SourceErrorClass.CONFIGURATION


@respx.mock
@pytest.mark.parametrize("body", [b"nope", b"[]", b'{"nojobs": 1}', b'{"jobs": {"a": 1}}'])
async def test_an_answer_without_a_job_list_is_invalid(body: bytes) -> None:
    respx.get(URL, params=PARAMS).respond(200, content=body)
    with pytest.raises(SourceError) as error:
        await build_ats(AshbyAdapter).collect(ats_checkpoint("synthco"))
    assert error.value.error_class is SourceErrorClass.INVALID_PAYLOAD


@respx.mock
async def test_a_server_error_is_retried_then_classified() -> None:
    route = respx.get(URL, params=PARAMS).respond(503)
    with pytest.raises(SourceError) as error:
        await build_ats(AshbyAdapter, Sleeper()).collect(ats_checkpoint("synthco"))
    assert error.value.error_class is SourceErrorClass.SERVER_ERROR
    assert route.call_count == 3


def test_type_and_endpoint() -> None:
    adapter = build_ats(AshbyAdapter)
    assert adapter.source_type is SourceType.ASHBY
    assert adapter.endpoint("synthco") == URL
