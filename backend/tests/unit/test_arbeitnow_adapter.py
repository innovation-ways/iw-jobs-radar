"""The Arbeitnow adapter against recorded synthetic payloads (ADR-049, research R-00173)."""

from datetime import UTC, datetime

import pytest
import respx
from tests.job_board_support import Scripted, Sleeper, build, checkpoint, payload

from jobs_radar.adapters.sources.arbeitnow import ArbeitnowAdapter
from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.schemas.source_filters import JobBoardFilters

URL = "https://www.arbeitnow.com/api/job-board-api"


def two_pages() -> Scripted:
    return Scripted(
        [
            ({"page": "1"}, 200, payload("arbeitnow", "page1.json")),
            ({"page": "2"}, 200, payload("arbeitnow", "page2.json")),
        ]
    )


@respx.mock
async def test_collect_keeps_what_passes_the_filters_and_follows_the_pages() -> None:
    board = two_pages()
    respx.get(URL).mock(side_effect=board)
    result = await build(ArbeitnowAdapter).collect(checkpoint("arbeitnow"))
    assert [p.external_job_id for p in result.postings] == [
        "backend-engineer-1",
        "data-engineer-2",
        "sre-remote-7",
    ]
    # Berlin on-site, Germany-only remote, a marketing role and a 40-day-old posting are left out.
    assert result.dropped_count == 4
    assert result.truncated is False
    assert result.outcome == "modified"
    assert result.etag is None
    assert [call["page"] for call in board.calls] == ["1", "2"]


@respx.mock
async def test_a_posting_is_mapped_with_its_company_text_and_dates() -> None:
    respx.get(URL).mock(side_effect=two_pages())
    result = await build(ArbeitnowAdapter).collect(checkpoint("arbeitnow"))
    posting = result.postings[0]
    assert posting.company_name == "Acme Robotics"
    assert posting.title == "Senior Backend Engineer"
    assert posting.source_url == "https://www.arbeitnow.com/jobs/companies/backend-engineer-1"
    assert posting.apply_url == posting.source_url
    assert "Build and run synthetic services." in posting.description_text
    assert "<" not in posting.description_text and "&lt;" not in posting.description_text
    assert posting.posted_at == datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
    assert posting.locations == ("Remote",)
    assert posting.departments == ("Software Development",)
    assert posting.raw_payload["slug"] == "backend-engineer-1"
    lisbon = result.postings[1]
    assert lisbon.locations == ("Lisbon",)


@respx.mock
async def test_the_per_run_limit_stops_the_scan_and_marks_the_run_truncated() -> None:
    board = two_pages()
    respx.get(URL).mock(side_effect=board)
    filters = JobBoardFilters(max_postings_per_run=2)
    result = await build(ArbeitnowAdapter).collect(checkpoint("arbeitnow", filters))
    assert len(result.postings) == 2
    assert result.truncated is True
    assert [call["page"] for call in board.calls] == ["1"]


@respx.mock
async def test_search_terms_keep_only_matching_postings() -> None:
    respx.get(URL).mock(side_effect=two_pages())
    filters = JobBoardFilters(search_terms=["data"])
    result = await build(ArbeitnowAdapter).collect(checkpoint("arbeitnow", filters))
    assert [p.external_job_id for p in result.postings] == ["data-engineer-2"]


@respx.mock
async def test_validate_reports_the_board_name_and_how_many_postings_match() -> None:
    respx.get(URL).mock(side_effect=two_pages())
    info = await build(ArbeitnowAdapter).validate("arbeitnow", filters=JobBoardFilters())
    assert info.name == "Arbeitnow"
    assert info.matching_count == 3
    assert info.postings_count == 7
    assert info.matching_is_lower_bound is False


def test_the_endpoint_comes_from_the_catalogue_and_the_type_is_arbeitnow() -> None:
    adapter = build(ArbeitnowAdapter)
    assert adapter.source_type is SourceType.ARBEITNOW
    assert adapter.endpoint("arbeitnow") == URL


async def test_an_identifier_other_than_the_catalogue_key_is_a_configuration_error() -> None:
    with pytest.raises(SourceError) as error:
        await build(ArbeitnowAdapter).collect(checkpoint("not-arbeitnow"))
    assert error.value.error_class is SourceErrorClass.CONFIGURATION


# --- failures --------------------------------------------------------------------------------------


@respx.mock
async def test_rate_limiting_is_retried_then_classified() -> None:
    route = respx.get(URL).respond(429, headers={"Retry-After": "5"})
    sleeper = Sleeper()
    with pytest.raises(SourceError) as error:
        await build(ArbeitnowAdapter, sleeper).collect(checkpoint("arbeitnow"))
    assert error.value.error_class is SourceErrorClass.RATE_LIMITED
    assert route.call_count == 3
    # The limiter's own 1 s spacing is also recorded; only the two Retry-After waits matter here.
    assert [wait for wait in sleeper.waits if wait == 5.0] == [5.0, 5.0]


@respx.mock
@pytest.mark.parametrize(
    ("status", "error_class"),
    [(500, SourceErrorClass.SERVER_ERROR), (404, SourceErrorClass.NOT_FOUND)],
)
async def test_http_failures_are_classified(status: int, error_class: SourceErrorClass) -> None:
    respx.get(URL).respond(status)
    with pytest.raises(SourceError) as error:
        await build(ArbeitnowAdapter).collect(checkpoint("arbeitnow"))
    assert error.value.error_class is error_class


@respx.mock
@pytest.mark.parametrize("body", [b"not json", b'{"nodata": []}', b'{"data": {"a": 1}}', b"[]"])
async def test_an_answer_that_is_not_a_job_list_is_invalid(body: bytes) -> None:
    respx.get(URL).respond(200, content=body)
    with pytest.raises(SourceError) as error:
        await build(ArbeitnowAdapter).collect(checkpoint("arbeitnow"))
    assert error.value.error_class is SourceErrorClass.INVALID_PAYLOAD


@respx.mock
async def test_a_single_malformed_posting_is_skipped_and_counted_not_fatal() -> None:
    body = b'{"data": [{"slug": "x"}, 5], "links": {"next": null}}'
    respx.get(URL).respond(200, content=body)
    result = await build(ArbeitnowAdapter).collect(checkpoint("arbeitnow"))
    assert result.postings == ()
    assert result.dropped_count == 2
