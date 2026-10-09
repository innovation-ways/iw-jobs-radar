"""The Himalayas adapter against recorded synthetic payloads (ADR-049, research R-00173)."""

import pytest
import respx
from tests.job_board_support import PORTUGAL, Scripted, build, checkpoint, payload

from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.adapters.sources.himalayas import HimalayasAdapter
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters

URL = "https://himalayas.app/jobs/api/search"
GUID = "https://himalayas.app/companies/"


def board(empty_pt: bool = False) -> Scripted:
    pt1 = "empty.json" if empty_pt else "country_pt_page1.json"
    return Scripted(
        [
            ({"country": "PT", "page": "2"}, 200, payload("himalayas", "country_pt_page2.json")),
            ({"country": "PT"}, 200, payload("himalayas", pt1)),
            ({"worldwide": "true"}, 200, payload("himalayas", "worldwide_page1.json")),
        ]
    )


@respx.mock
async def test_collect_reads_the_country_and_worldwide_streams_and_filters() -> None:
    scripted = board()
    respx.get(URL).mock(side_effect=scripted)
    result = await build(HimalayasAdapter).collect(checkpoint("himalayas"))
    assert [p.external_job_id for p in result.postings] == [
        GUID + "acme/jobs/backend-engineer",
        GUID + "globex/jobs/data-scientist",
        GUID + "soylent/jobs/platform-engineer",
    ]
    # A sales role and a 40-day-old security role are left out.
    assert result.dropped_count == 2
    assert result.declared_total == 5
    assert result.truncated is False
    assert [(c.get("country"), c.get("worldwide"), c["page"]) for c in scripted.calls] == [
        ("PT", None, "1"),
        ("PT", None, "2"),
        (None, "true", "1"),
    ]
    assert all(call["sort"] == "recent" and call["limit"] == "20" for call in scripted.calls)
    assert all(
        call.get("exclude_worldwide") == "true" for call in scripted.calls if "country" in call
    )


@respx.mock
async def test_a_posting_is_mapped_with_company_places_salary_and_dates() -> None:
    respx.get(URL).mock(side_effect=board())
    result = await build(HimalayasAdapter).collect(checkpoint("himalayas"))
    posting = result.postings[0]
    assert posting.company_name == "Acme Robotics"
    assert posting.source_url == GUID + "acme/jobs/backend-engineer"
    assert posting.locations == ("Portugal", "Spain")
    assert posting.departments == ("Engineering",)
    assert "Build synthetic things." in posting.description_text
    assert "55000" in posting.description_text and "75000" in posting.description_text
    assert "EUR" in posting.description_text
    assert posting.posted_at is not None
    # Restrictions given as objects are read like names.
    assert result.postings[1].locations == ("Portugal",)
    # No restriction means open worldwide.
    assert result.postings[2].locations == ("Worldwide",)


@respx.mock
async def test_without_worldwide_only_the_country_stream_is_requested() -> None:
    scripted = board()
    respx.get(URL).mock(side_effect=scripted)
    scope = LocationScope(frozenset({"PT"}), include_worldwide=False)
    result = await build(HimalayasAdapter).collect(checkpoint("himalayas", scope=scope))
    assert len(result.postings) == 2
    assert all("worldwide" not in call for call in scripted.calls)


@respx.mock
async def test_each_country_is_its_own_stream() -> None:
    scripted = Scripted(
        [
            ({"country": "PT"}, 200, payload("himalayas", "country_pt_page2.json")),
            ({"country": "ES"}, 200, payload("himalayas", "empty.json")),
        ]
    )
    respx.get(URL).mock(side_effect=scripted)
    filters = JobBoardFilters(categories=[])
    scope = LocationScope(frozenset({"PT", "ES"}), include_worldwide=False)
    result = await build(HimalayasAdapter).collect(checkpoint("himalayas", filters, scope))
    assert [p.company_name for p in result.postings] == ["Hooli"]
    assert {call["country"] for call in scripted.calls} == {"PT", "ES"}


@respx.mock
async def test_the_per_run_limit_truncates_the_run() -> None:
    respx.get(URL).mock(side_effect=board())
    filters = JobBoardFilters(max_postings_per_run=1)
    result = await build(HimalayasAdapter).collect(checkpoint("himalayas", filters))
    assert len(result.postings) == 1
    assert result.truncated is True


@respx.mock
async def test_validate_reports_the_declared_total_and_matches() -> None:
    respx.get(URL).mock(side_effect=board())
    info = await build(HimalayasAdapter).validate(
        "himalayas", filters=JobBoardFilters(), scope=PORTUGAL
    )
    assert (info.name, info.postings_count, info.matching_count) == ("Himalayas", 5, 3)


def test_type_and_endpoint() -> None:
    adapter = build(HimalayasAdapter)
    assert adapter.source_type is SourceType.HIMALAYAS
    assert adapter.endpoint("himalayas") == "https://himalayas.app/jobs/api"


@respx.mock
@pytest.mark.parametrize("body", [b"nope", b'{"totalCount": 1}', b'{"jobs": {"a": 1}}', b"[]"])
async def test_an_unusable_answer_is_invalid(body: bytes) -> None:
    respx.get(URL).respond(200, content=body)
    with pytest.raises(SourceError) as error:
        await build(HimalayasAdapter).collect(checkpoint("himalayas"))
    assert error.value.error_class is SourceErrorClass.INVALID_PAYLOAD


@respx.mock
async def test_too_many_requests_is_classified() -> None:
    respx.get(URL).respond(429)
    with pytest.raises(SourceError) as error:
        await build(HimalayasAdapter).collect(checkpoint("himalayas"))
    assert error.value.error_class is SourceErrorClass.RATE_LIMITED


@respx.mock
async def test_remote_work_from_anywhere_reads_the_newest_postings_of_every_country() -> None:
    scripted = Scripted([({}, 200, payload("himalayas", "worldwide_page1.json"))])
    respx.get(URL).mock(side_effect=scripted)
    scope = LocationScope(include_worldwide=True, any_country=True)
    await build(HimalayasAdapter).collect(checkpoint("himalayas", scope=scope))
    assert len(scripted.calls) == 1
    assert "country" not in scripted.calls[0] and "worldwide" not in scripted.calls[0]


@pytest.mark.parametrize("scope", [None, LocationScope()])
async def test_without_a_known_location_nothing_is_collected(scope: LocationScope | None) -> None:
    with pytest.raises(SourceError) as error:
        await build(HimalayasAdapter).collect(checkpoint("himalayas", scope=scope))
    assert error.value.error_class is SourceErrorClass.CONFIGURATION
    assert "Profile & intent" in error.value.message
