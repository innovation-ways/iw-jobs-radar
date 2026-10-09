"""The SmartRecruiters adapter against recorded synthetic payloads (ADR-050, research R-00169)."""

from datetime import UTC, datetime

import httpx
import pytest
import respx
from tests.job_board_support import Scripted, ats_checkpoint, build_ats, payload

from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.adapters.sources.smartrecruiters import SmartRecruitersAdapter
from jobs_radar.domain.enums import SourceErrorClass, SourceType

BASE = "https://api.smartrecruiters.com/v1/companies/SynthCo/postings"


def serve(listing_pages: bool = True) -> Scripted:
    """Mock the list and the detail endpoints; any unexpected request answers 599."""
    routes = [
        ({"offset": "0", "limit": "100"}, 200, payload("smartrecruiters", "list_p1.json")),
        ({"offset": "3", "limit": "100"}, 200, payload("smartrecruiters", "list_p2.json")),
    ]
    scripted = Scripted(routes if listing_pages else [])
    respx.get(BASE).mock(side_effect=scripted)
    for number in (1, 4, 5):
        respx.get(f"{BASE}/7440001547{number:05d}").respond(
            200, content=payload("smartrecruiters", f"detail_{number}.json")
        )
    return scripted


@respx.mock
async def test_collect_reads_the_details_of_the_technology_postings_only() -> None:
    scripted = serve()
    result = await build_ats(SmartRecruitersAdapter).collect(ats_checkpoint("SynthCo"))
    assert [p.external_job_id for p in result.postings] == [
        "744000154700001",
        "744000154700004",
        "744000154700005",
    ]
    assert result.declared_total == 5
    assert result.dropped_count == 2  # the HR and marketing roles
    assert result.truncated is False
    assert result.etag is None
    assert [call["offset"] for call in scripted.calls] == ["0", "3"]


@respx.mock
async def test_a_posting_is_mapped_from_its_detail() -> None:
    serve()
    result = await build_ats(SmartRecruitersAdapter).collect(ats_checkpoint("SynthCo"))
    first, second, _ = result.postings
    assert first.title == "Senior DevOps Engineer"
    assert first.source_url == "https://jobs.smartrecruiters.com/SynthCo/744000154700001-slug"
    assert first.apply_url.endswith("?oga=true")
    assert first.posted_at == datetime(2026, 10, 8, 10, 0, tzinfo=UTC)
    assert first.language == "en"
    assert first.locations == ("Lisbon, Portugal", "Hybrid")
    assert first.departments == ("Information Technology", "Core")
    assert first.company_name is None
    for text in ("You will run pipelines.", "Python and SQL.", "Flexible hours."):
        assert text in first.description_text
    assert "<" not in first.description_text
    assert second.locations == ("Lisbon, Portugal", "Remote")


@respx.mock
async def test_the_detail_limit_truncates_the_run() -> None:
    serve()
    result = await build_ats(SmartRecruitersAdapter, max_details=2).collect(
        ats_checkpoint("SynthCo")
    )
    assert len(result.postings) == 2
    assert result.truncated is True


@respx.mock
async def test_a_posting_that_vanished_between_list_and_detail_is_skipped() -> None:
    serve()
    respx.get(f"{BASE}/744000154700004").respond(404)
    result = await build_ats(SmartRecruitersAdapter).collect(ats_checkpoint("SynthCo"))
    assert [p.external_job_id for p in result.postings] == ["744000154700001", "744000154700005"]


@respx.mock
async def test_validate_names_the_company_and_counts_postings() -> None:
    respx.get(BASE, params={"limit": "1"}).respond(
        200,
        json={
            "offset": 0,
            "limit": 1,
            "totalFound": 5,
            "content": [{"company": {"identifier": "SynthCo", "name": "Synth Co"}}],
        },
    )
    info = await build_ats(SmartRecruitersAdapter).validate("SynthCo")
    assert (info.name, info.postings_count) == ("Synth Co", 5)


@respx.mock
async def test_a_company_without_postings_is_not_found() -> None:
    # SmartRecruiters answers 200 with nothing for an unknown company.
    respx.get(BASE, params={"limit": "1"}).respond(
        200, content=payload("smartrecruiters", "empty.json")
    )
    with pytest.raises(SourceError) as error:
        await build_ats(SmartRecruitersAdapter).validate("SynthCo")
    assert error.value.error_class is SourceErrorClass.NOT_FOUND


@pytest.mark.parametrize("token", ["", "has space", "../etc", "a/b", "x" * 101, "token?x=1"])
async def test_an_invalid_identifier_is_rejected_without_any_request(token: str) -> None:
    with respx.mock(assert_all_called=False) as router:
        with pytest.raises(SourceError) as error:
            await build_ats(SmartRecruitersAdapter).validate(token)
        assert router.calls.call_count == 0
    assert error.value.error_class is SourceErrorClass.CONFIGURATION


@respx.mock
@pytest.mark.parametrize("body", [b"nope", b"[]", b'{"content": {"a": 1}}', b'{"nocontent": 1}'])
async def test_an_unusable_list_is_invalid(body: bytes) -> None:
    respx.get(BASE).mock(return_value=httpx.Response(200, content=body))
    with pytest.raises(SourceError) as error:
        await build_ats(SmartRecruitersAdapter).collect(ats_checkpoint("SynthCo"))
    assert error.value.error_class is SourceErrorClass.INVALID_PAYLOAD


@respx.mock
async def test_a_server_error_on_a_detail_fails_the_run() -> None:
    serve()
    respx.get(f"{BASE}/744000154700004").respond(500)
    with pytest.raises(SourceError) as error:
        await build_ats(SmartRecruitersAdapter).collect(ats_checkpoint("SynthCo"))
    assert error.value.error_class is SourceErrorClass.SERVER_ERROR


def test_type_and_endpoint() -> None:
    adapter = build_ats(SmartRecruitersAdapter)
    assert adapter.source_type is SourceType.SMARTRECRUITERS
    assert adapter.endpoint("SynthCo") == BASE


@respx.mock
async def test_listing_stops_once_more_postings_are_known_than_can_be_read() -> None:
    page = {
        "offset": 0,
        "limit": 100,
        "totalFound": 5000,
        "content": [
            {
                "id": "744000154700001",
                "name": "DevOps Engineer",
                "function": {"id": "information_technology"},
            },
            {
                "id": "744000154700005",
                "name": "Data Platform Lead",
                "function": {"id": "information_technology"},
            },
        ],
    }
    scripted = Scripted([({"offset": "0"}, 200, __import__("json").dumps(page).encode())])
    respx.get(BASE).mock(side_effect=scripted)
    respx.get(f"{BASE}/744000154700001").respond(
        200, content=payload("smartrecruiters", "detail_1.json")
    )
    result = await build_ats(SmartRecruitersAdapter, max_details=1).collect(
        ats_checkpoint("SynthCo")
    )
    assert len(scripted.calls) == 1  # the other 4,998 postings are not even listed
    assert len(result.postings) == 1 and result.truncated is True


@respx.mock
async def test_with_a_location_scope_only_the_owners_countries_are_listed() -> None:
    from dataclasses import replace

    from jobs_radar.domain.job_board_rules import LocationScope

    scripted = Scripted(
        [
            ({"country": "pt", "offset": "0"}, 200, payload("smartrecruiters", "list_p2.json")),
            (
                {"country": "pt", "offset": "2"},
                200,
                b'{"offset": 2, "limit": 100, "totalFound": 2, "content": []}',
            ),
        ]
    )
    respx.get(BASE).mock(side_effect=scripted)
    for number in (4, 5):
        respx.get(f"{BASE}/7440001547{number:05d}").respond(
            200, content=payload("smartrecruiters", f"detail_{number}.json")
        )
    scope = LocationScope(frozenset({"PT"}), include_worldwide=True)
    checkpoint = replace(ats_checkpoint("SynthCo"), scope=scope)
    result = await build_ats(SmartRecruitersAdapter).collect(checkpoint)
    assert {call.get("country") for call in scripted.calls} == {"pt"}
    assert [p.external_job_id for p in result.postings] == ["744000154700004", "744000154700005"]


@respx.mock
async def test_remote_work_from_anywhere_lists_every_country() -> None:
    from dataclasses import replace

    from jobs_radar.domain.job_board_rules import LocationScope

    scripted = serve()
    scope = LocationScope(frozenset({"PT"}), include_worldwide=True, any_country=True)
    await build_ats(SmartRecruitersAdapter).collect(replace(ats_checkpoint("SynthCo"), scope=scope))
    assert all("country" not in call for call in scripted.calls)


@respx.mock
async def test_the_owners_areas_decide_which_details_are_read() -> None:
    from dataclasses import replace

    from jobs_radar.schemas.source_filters import JobBoardFilters

    serve()
    # "Senior DevOps Engineer" and "Data Platform Lead" are technical, but only data is wanted:
    # no detail of the DevOps role (or of the HR and marketing roles) is requested.
    filters = JobBoardFilters(categories=["data"])
    checkpoint = replace(ats_checkpoint("SynthCo"), filters=filters)
    result = await build_ats(SmartRecruitersAdapter).collect(checkpoint)
    assert [p.external_job_id for p in result.postings] == ["744000154700005"]
    assert result.truncated is False
