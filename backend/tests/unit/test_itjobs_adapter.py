"""The ITJobs.pt adapter against recorded synthetic payloads shaped as documented (ADR-049, T9.6).

The payloads follow the public documentation of ``job/list.json``; no real key was available, so
the shapes still need a check against the live service (``make smoke`` with a key).
"""

import pytest
import respx
from tests.job_board_support import PORTUGAL, Scripted, build, checkpoint, payload

from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.adapters.sources.itjobs import ItJobsAdapter
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.schemas.source_filters import JobBoardFilters

URL = "https://api.itjobs.pt/job/list.json"
KEY = "synthetic-key-123"


def pages() -> Scripted:
    return Scripted(
        [
            ({"page": "1", "api_key": KEY}, 200, payload("itjobs", "list_p1.json")),
            ({"page": "2", "api_key": KEY}, 200, payload("itjobs", "list_p2.json")),
        ]
    )


def keyed(identifier: str = "itjobs_pt"):
    base = checkpoint(identifier)
    from dataclasses import replace

    return replace(base, credential=KEY)


@respx.mock
async def test_collect_keeps_what_passes_the_filters_and_follows_the_pages() -> None:
    scripted = pages()
    respx.get(URL).mock(side_effect=scripted)
    result = await build(ItJobsAdapter).collect(keyed())
    # Lisbon backend (inside 40 km) and the remote job stay; Porto on site is outside the radius
    # and the marketing role has no technology area.
    assert [p.external_job_id for p in result.postings] == ["101", "102"]
    assert result.dropped_count == 2
    assert result.declared_total == 4
    assert result.truncated is False
    assert [(c["page"], c["limit"]) for c in scripted.calls] == [("1", "100"), ("2", "100")]


@respx.mock
async def test_a_posting_is_mapped_with_its_company_places_and_salary() -> None:
    respx.get(URL).mock(side_effect=pages())
    first, second = (await build(ItJobsAdapter).collect(keyed())).postings
    assert first.company_name == "Synth Co"
    assert first.title == "Backend Engineer"
    assert first.locations == ("Lisboa",)
    assert first.departments == ("Programação",)
    assert first.source_url == "https://www.itjobs.pt/oferta/101/backend-engineer"
    assert "Build services in Python." in first.description_text
    assert "30000" in first.description_text and "45000" in first.description_text
    assert first.posted_at is not None and first.posted_at.year == 2026
    assert second.company_name == "Globex"
    assert second.locations == ("Porto", "Remoto")


@respx.mock
async def test_the_key_goes_in_the_request_but_never_in_the_result() -> None:
    respx.get(URL).mock(side_effect=pages())
    result = await build(ItJobsAdapter).collect(keyed())
    assert KEY not in repr(result)
    assert all(KEY not in p.source_url and KEY not in p.apply_url for p in result.postings)


@respx.mock
async def test_without_a_key_nothing_is_requested() -> None:
    with pytest.raises(SourceError) as error:
        await build(ItJobsAdapter).collect(checkpoint("itjobs_pt"))
    assert error.value.error_class is SourceErrorClass.AUTHENTICATION


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_key_is_an_authentication_error(status: int) -> None:
    respx.get(URL).respond(status)
    with pytest.raises(SourceError) as error:
        await build(ItJobsAdapter).collect(keyed())
    assert error.value.error_class is SourceErrorClass.AUTHENTICATION
    assert KEY not in error.value.message


@respx.mock
async def test_an_error_answer_with_status_200_is_an_authentication_error() -> None:
    respx.get(URL).respond(200, content=payload("itjobs", "bad_key.json"))
    with pytest.raises(SourceError) as error:
        await build(ItJobsAdapter).collect(keyed())
    assert error.value.error_class is SourceErrorClass.AUTHENTICATION


@respx.mock
@pytest.mark.parametrize("body", [b"nope", b"[]", b'{"results": {"a": 1}}', b'{"total": 1}'])
async def test_an_unusable_answer_is_invalid(body: bytes) -> None:
    respx.get(URL).respond(200, content=body)
    with pytest.raises(SourceError) as error:
        await build(ItJobsAdapter).collect(keyed())
    assert error.value.error_class is SourceErrorClass.INVALID_PAYLOAD


@respx.mock
async def test_the_per_run_limit_truncates_the_run() -> None:
    respx.get(URL).mock(side_effect=pages())
    from dataclasses import replace

    cp = replace(keyed(), filters=JobBoardFilters(max_postings_per_run=1))
    result = await build(ItJobsAdapter).collect(cp)
    assert len(result.postings) == 1 and result.truncated is True


@respx.mock
async def test_validate_checks_the_key_and_reports_matches() -> None:
    respx.get(URL).mock(side_effect=pages())
    info = await build(ItJobsAdapter).validate(
        "itjobs_pt", credential=KEY, filters=JobBoardFilters(), scope=PORTUGAL
    )
    assert (info.name, info.postings_count, info.matching_count) == ("ITJobs.pt", 4, 2)


async def test_validate_without_a_key_is_refused() -> None:
    with pytest.raises(SourceError) as error:
        await build(ItJobsAdapter).validate("itjobs_pt", scope=PORTUGAL)
    assert error.value.error_class is SourceErrorClass.AUTHENTICATION


def test_type_and_endpoint_never_contain_the_key() -> None:
    adapter = build(ItJobsAdapter)
    assert adapter.source_type is SourceType.ITJOBS_PT
    assert adapter.endpoint("itjobs_pt") == URL
