"""The Eightfold adapter against recorded synthetic payloads (ADR-055)."""

from datetime import UTC, datetime

import pytest
import respx
from tests.job_board_support import Scripted, build_ats, checkpoint, payload

from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.adapters.sources.eightfold import EightfoldAdapter, map_posting
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters

HOST = "jobs.synthco.example"
SEARCH = f"https://{HOST}/api/pcsx/search"
DETAIL = f"https://{HOST}/api/pcsx/position_details"


def serve(*, pages: bool = True) -> Scripted:
    """Mock the search and the detail endpoints; any unexpected request answers 599."""
    routes = (
        [
            ({"start": "0"}, 200, payload("eightfold", "search_p1.json")),
            ({"start": "3"}, 200, payload("eightfold", "search_p2.json")),
        ]
        if pages
        else []
    )
    scripted = Scripted(routes)
    respx.get(SEARCH).mock(side_effect=scripted)
    for number in (1, 2, 4):
        respx.get(DETAIL, params={"position_id": str(90000000000 + number)}).respond(
            200, content=payload("eightfold", f"detail_{number}.json")
        )
    for number in (3, 5):  # these two closed between the list and the detail
        respx.get(DETAIL, params={"position_id": str(90000000000 + number)}).respond(404)
    return scripted


def run(identifier: str = HOST, filters: JobBoardFilters | None = None, scope=None, **kwargs):
    """Collect with an adapter built for the tests."""
    return build_ats(EightfoldAdapter, **kwargs).collect(checkpoint(identifier, filters, scope))


def test_the_endpoint_is_the_search_address_of_the_careers_site() -> None:
    assert EightfoldAdapter.endpoint(build_ats(EightfoldAdapter), HOST) == SEARCH
    assert build_ats(EightfoldAdapter).source_type is SourceType.EIGHTFOLD


@pytest.mark.parametrize(
    "identifier",
    ["synthco", "synthco.example", "jobs..example", "jobs.syn thco.example", "a/b.c.d"],
)
async def test_a_careers_address_without_a_company_domain_is_refused(identifier: str) -> None:
    with pytest.raises(SourceError) as caught:
        await run(identifier)
    assert caught.value.error_class is SourceErrorClass.CONFIGURATION


@respx.mock
async def test_without_filters_the_details_of_every_listed_posting_are_read() -> None:
    serve()
    result = await run()
    assert len([c for c in respx.calls if c.request.url.path.endswith("position_details")]) == 5
    assert result.dropped_count == 2  # the two that closed between the list and the detail
    assert result.declared_total == 5


@respx.mock
async def test_the_domain_is_the_careers_address_without_its_first_label() -> None:
    scripted = serve()
    await run()
    assert {call["domain"] for call in scripted.calls} == {"synthco.example"}


@respx.mock
async def test_the_listing_is_read_page_by_page_newest_first() -> None:
    scripted = serve()
    await run()
    assert [(call["start"], call["sort_by"]) for call in scripted.calls] == [
        ("0", "timestamp"),
        ("3", "timestamp"),
    ]


@respx.mock
async def test_a_posting_is_mapped_from_its_detail() -> None:
    serve()
    result = await run()
    assert [p.external_job_id for p in result.postings] == [
        "90000000001",
        "90000000002",
        "90000000004",
    ]
    first, second, third = result.postings
    assert first.title == "Senior Billing Solution Architect"
    assert first.source_url == f"https://{HOST}/careers/job/90000000001"
    assert first.apply_url == first.source_url
    assert first.posted_at == datetime.fromtimestamp(1791000000, UTC)
    assert first.locations == ("Lisbon, Portugal", "Hybrid")
    assert first.departments == ("Delivery",)
    assert "You will design billing solutions." in first.description_text
    assert "Convergent charging" in first.description_text
    assert "<" not in first.description_text
    assert second.locations == ("Remote - Portugal", "Remote")
    assert third.departments == ()
    assert first.company_name is None


@respx.mock
async def test_the_chosen_areas_decide_which_details_are_read() -> None:
    serve()
    filters = JobBoardFilters(categories=["software"])
    result = await run(filters=filters)
    # Only the architect's and the engineer's titles name the software area.
    assert [p.external_job_id for p in result.postings] == ["90000000001", "90000000002"]
    assert result.dropped_count == 3
    assert result.truncated is False


@respx.mock
async def test_the_owners_countries_narrow_the_listing() -> None:
    scripted = Scripted(
        [
            ({"location": "Portugal", "start": "0"}, 200, payload("eightfold", "search_p1.json")),
            ({"location": "Portugal"}, 200, payload("eightfold", "search_empty.json")),
            ({"location": "Remote"}, 200, payload("eightfold", "search_empty.json")),
        ]
    )
    respx.get(SEARCH).mock(side_effect=scripted)
    scope = LocationScope(frozenset({"PT"}), include_worldwide=False)
    await run(filters=JobBoardFilters(categories=["devops"]), scope=scope)
    assert {call["location"] for call in scripted.calls} == {"Portugal", "Remote"}


@respx.mock
async def test_remote_work_from_anywhere_lists_every_country() -> None:
    scripted = serve()
    scope = LocationScope(frozenset({"PT"}), any_country=True)
    await run(scope=scope)
    assert all("location" not in call for call in scripted.calls)


@respx.mock
async def test_one_listing_per_country_without_repeating_a_posting() -> None:
    scripted = Scripted(
        [
            ({"location": "Portugal", "start": "0"}, 200, payload("eightfold", "search_p1.json")),
            ({"location": "Portugal"}, 200, payload("eightfold", "search_empty.json")),
            ({"location": "Spain", "start": "0"}, 200, payload("eightfold", "search_p1.json")),
            ({"location": "Spain"}, 200, payload("eightfold", "search_empty.json")),
            ({"location": "Remote"}, 200, payload("eightfold", "search_empty.json")),
        ]
    )
    respx.get(SEARCH).mock(side_effect=scripted)
    scope = LocationScope(frozenset({"PT", "ES"}))
    result = await run(filters=JobBoardFilters(categories=["devops"]), scope=scope)
    assert {call["location"] for call in scripted.calls} == {"Portugal", "Spain", "Remote"}
    assert result.dropped_count == 3  # the same three postings, counted once


@respx.mock
async def test_the_detail_limit_truncates_the_run() -> None:
    serve()
    result = await run(max_details=2)
    assert len(result.postings) == 2
    assert result.truncated is True


@respx.mock
async def test_a_listing_longer_than_the_page_limit_truncates_the_run() -> None:
    scripted = serve()
    result = await run(max_pages=1)
    assert [call["start"] for call in scripted.calls[:1]] == ["0"]
    assert result.truncated is True
    assert result.declared_total == 5


@respx.mock
async def test_a_posting_that_vanished_between_list_and_detail_is_skipped() -> None:
    serve()
    result = await run()
    assert "90000000003" not in [p.external_job_id for p in result.postings]
    assert result.dropped_count == 2


@respx.mock
async def test_an_answer_with_an_unexpected_shape_is_refused() -> None:
    respx.get(SEARCH).respond(200, json={"data": {"positions": "nope", "count": 1}})
    with pytest.raises(SourceError) as caught:
        await run()
    assert caught.value.error_class is SourceErrorClass.INVALID_PAYLOAD


@respx.mock
async def test_validate_counts_the_postings_and_guesses_the_company_name() -> None:
    respx.get(SEARCH).respond(200, content=payload("eightfold", "search_p1.json"))
    info = await build_ats(EightfoldAdapter).validate(HOST)
    assert (info.name, info.postings_count) == ("Synthco", 5)


@respx.mock
async def test_validate_refuses_a_site_that_is_not_an_eightfold_careers_site() -> None:
    respx.get(SEARCH).respond(200, content=payload("eightfold", "not_eightfold.json"))
    with pytest.raises(SourceError) as caught:
        await build_ats(EightfoldAdapter).validate(HOST)
    assert caught.value.error_class is SourceErrorClass.NOT_FOUND


@respx.mock
async def test_validate_refuses_a_company_without_postings() -> None:
    respx.get(SEARCH).respond(200, content=payload("eightfold", "search_empty.json"))
    with pytest.raises(SourceError) as caught:
        await build_ats(EightfoldAdapter).validate(HOST)
    assert caught.value.error_class is SourceErrorClass.NOT_FOUND


def _remote_detail(**changes: object) -> dict[str, object]:
    detail: dict[str, object] = {
        "id": 90000000009,
        "name": "Remote Billing Engineer",
        "locations": ["Hungary"],
        "standardizedLocations": ["HU"],
        "workLocationOption": "remote_local",
        "positionUrl": "/careers/job/90000000009",
        "jobDescription": "<p>Work from home.</p>",
    }
    return {**detail, **changes}


def test_remote_work_within_a_country_names_that_country() -> None:
    # Eightfold's "remote_local" means remote inside the posting's own country, never anywhere.
    posting = map_posting(_remote_detail(), HOST)
    assert posting.locations == ("Hungary", "Remote - HU")


def test_remote_work_without_a_country_is_plain_remote() -> None:
    posting = map_posting(_remote_detail(standardizedLocations=[]), HOST)
    assert posting.locations == ("Hungary", "Remote")


def test_remote_work_in_several_countries_names_each_one() -> None:
    posting = map_posting(
        _remote_detail(
            locations=["Berlin, Germany", "Paris, France"],
            standardizedLocations=["Berlin, Berlin, DE", "FR"],
        ),
        HOST,
    )
    assert posting.locations == ("Berlin, Germany", "Paris, France", "Remote - DE", "Remote - FR")
