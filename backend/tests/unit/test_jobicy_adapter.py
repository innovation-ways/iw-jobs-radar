"""The Jobicy adapter against recorded synthetic payloads (ADR-049, research R-00173)."""

import pytest
import respx
from tests.job_board_support import PORTUGAL, Scripted, build, checkpoint, payload

from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.adapters.sources.jobicy import JobicyAdapter
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters

URL = "https://jobicy.com/api/v2/remote-jobs"


def board() -> Scripted:
    return Scripted(
        [
            ({"geo": "europe", "cursor": "CURSOR2"}, 200, payload("jobicy", "europe_page2.json")),
            ({"geo": "europe"}, 200, payload("jobicy", "europe_page1.json")),
            ({"geo": "anywhere"}, 200, payload("jobicy", "anywhere_page1.json")),
        ]
    )


@respx.mock
async def test_collect_reads_the_europe_and_anywhere_streams_and_filters() -> None:
    scripted = board()
    respx.get(URL).mock(side_effect=scripted)
    result = await build(JobicyAdapter).collect(checkpoint("jobicy"))
    assert [p.external_job_id for p in result.postings] == ["5001", "5004", "6001"]
    # A sales role, a Germany-only analyst and a 40-day-old security role are left out.
    assert result.dropped_count == 3
    assert result.truncated is False
    assert [(c["geo"], c.get("cursor")) for c in scripted.calls] == [
        ("europe", None),
        ("europe", "CURSOR2"),
        ("anywhere", None),
    ]
    assert all(call["count"] == "100" for call in scripted.calls)


@respx.mock
async def test_a_posting_is_mapped_with_company_text_salary_and_dates() -> None:
    respx.get(URL).mock(side_effect=board())
    result = await build(JobicyAdapter).collect(checkpoint("jobicy"))
    posting = result.postings[0]
    assert posting.company_name == "Acme Robotics"
    assert posting.source_url == "https://jobicy.com/jobs/5001-senior-python-developer"
    assert posting.apply_url == posting.source_url
    assert "Work on synthetic systems." in posting.description_text
    assert "60000" in posting.description_text and "EUR" in posting.description_text
    assert posting.locations == ("Europe",)
    assert posting.departments == ("Engineering",)
    assert posting.posted_at is not None and posting.posted_at.year == 2026
    assert posting.raw_payload["id"] == 5001


@respx.mock
async def test_without_worldwide_only_the_europe_stream_is_requested() -> None:
    scripted = board()
    respx.get(URL).mock(side_effect=scripted)
    scope = LocationScope(frozenset({"PT"}), include_worldwide=False)
    result = await build(JobicyAdapter).collect(checkpoint("jobicy", scope=scope))
    assert [p.external_job_id for p in result.postings] == ["5001", "5004"]
    assert {call["geo"] for call in scripted.calls} == {"europe"}


@respx.mock
async def test_a_country_outside_europe_uses_its_own_geo_slug() -> None:
    scripted = Scripted([({"geo": "usa"}, 200, payload("jobicy", "anywhere_page1.json"))])
    respx.get(URL).mock(side_effect=scripted)
    scope = LocationScope(frozenset({"US"}), include_worldwide=False)
    await build(JobicyAdapter).collect(checkpoint("jobicy", scope=scope))
    assert {call["geo"] for call in scripted.calls} == {"usa"}


@respx.mock
async def test_the_per_run_limit_truncates_the_run() -> None:
    respx.get(URL).mock(side_effect=board())
    filters = JobBoardFilters(max_postings_per_run=1)
    result = await build(JobicyAdapter).collect(checkpoint("jobicy", filters))
    assert len(result.postings) == 1
    assert result.truncated is True


@respx.mock
async def test_validate_reports_matches() -> None:
    respx.get(URL).mock(side_effect=board())
    info = await build(JobicyAdapter).validate("jobicy", filters=JobBoardFilters(), scope=PORTUGAL)
    assert (info.name, info.matching_count) == ("Jobicy", 3)


def test_type_and_endpoint() -> None:
    adapter = build(JobicyAdapter)
    assert adapter.source_type is SourceType.JOBICY
    assert adapter.endpoint("jobicy") == URL


@respx.mock
@pytest.mark.parametrize(
    "body", [b"nope", b'{"success": false, "jobs": []}', b'{"success": true}', b"[]"]
)
async def test_an_unusable_answer_is_invalid(body: bytes) -> None:
    respx.get(URL).respond(200, content=body)
    with pytest.raises(SourceError) as error:
        await build(JobicyAdapter).collect(checkpoint("jobicy"))
    assert error.value.error_class is SourceErrorClass.INVALID_PAYLOAD


@respx.mock
async def test_a_server_error_is_classified() -> None:
    respx.get(URL).respond(503)
    with pytest.raises(SourceError) as error:
        await build(JobicyAdapter).collect(checkpoint("jobicy"))
    assert error.value.error_class is SourceErrorClass.SERVER_ERROR


def test_geo_slugs_follow_the_scope() -> None:
    from jobs_radar.adapters.sources.jobicy import geo_slugs

    assert geo_slugs(LocationScope(frozenset({"PT", "ES"}), include_worldwide=True)) == [
        "europe",
        "anywhere",
    ]
    assert geo_slugs(LocationScope(frozenset({"PT"}), include_worldwide=False)) == ["europe"]
    assert geo_slugs(LocationScope(frozenset({"CA"}), include_worldwide=False)) == ["canada"]
    assert geo_slugs(LocationScope(any_country=True)) == ["europe", "anywhere"]
