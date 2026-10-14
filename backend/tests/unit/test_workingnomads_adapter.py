"""The Working Nomads adapter against a recorded synthetic payload (ADR-074, research R-00176)."""

import httpx
import pytest
import respx
from tests.job_board_support import PORTUGAL, build, checkpoint, payload

from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.adapters.sources.workingnomads import WorkingNomadsAdapter
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters

URL = "https://www.workingnomads.com/api/exposed_jobs/"
SEARCH = "https://www.workingnomads.com/jobsapi/_search"
PAGE = "https://www.workingnomads.com/jobs?job="


def board(*, search: httpx.Response | None = None) -> respx.Route:
    """Mock the feed and the site's own search (which holds each posting's page slug)."""
    respx.get(SEARCH).mock(
        return_value=search or httpx.Response(200, content=payload("workingnomads", "search.json"))
    )
    return respx.get(URL).mock(
        return_value=httpx.Response(200, content=payload("workingnomads", "exposed_jobs.json"))
    )


def test_the_adapter_is_a_catalogue_job_board() -> None:
    assert WorkingNomadsAdapter.source_type is SourceType.WORKINGNOMADS
    assert WorkingNomadsAdapter.entry.catalogue_key == "workingnomads"


@respx.mock
async def test_collect_reads_the_feed_once_and_filters() -> None:
    route = board()
    result = await build(WorkingNomadsAdapter).collect(checkpoint("workingnomads"))
    assert route.call_count == 1
    assert [p.company_name for p in result.postings] == ["Acme Systems", "Globex", "Initech"]
    # A US-only role, a sales role, an old role and a posting without company.
    assert result.dropped_count == 4
    assert result.truncated is False
    assert result.outcome == "modified"


@respx.mock
async def test_a_posting_is_mapped_with_url_text_tags_and_date() -> None:
    board()
    result = await build(WorkingNomadsAdapter).collect(checkpoint("workingnomads"))
    posting = result.postings[0]
    # The feed URL redirects to the employer's application form; the page that shows the
    # posting is /jobs?job=<slug>, and the slug is the site's own (it is not derivable).
    assert posting.external_job_id == "https://www.workingnomads.com/job/go/1000001/"
    assert posting.apply_url == posting.external_job_id
    assert posting.source_url == PAGE + "senior-python-engineer-acme-systems-1000001"
    assert posting.title == "Senior Backend Engineer (Contract)"
    assert "Day rate EUR 500-600" in posting.description_text
    assert posting.locations == ("Global",)
    assert posting.departments == ("Development",)
    assert posting.posted_at is not None and posting.posted_at.year == 2026


@respx.mock
async def test_without_worldwide_a_global_posting_is_left_out() -> None:
    board()
    scope = LocationScope(frozenset({"PT"}), include_worldwide=False)
    result = await build(WorkingNomadsAdapter).collect(checkpoint("workingnomads", scope=scope))
    # Europe names Portugal; the unreadable time zone is kept for the later judgement.
    assert [p.company_name for p in result.postings] == ["Globex", "Initech"]


@respx.mock
async def test_the_per_run_limit_truncates_the_run() -> None:
    board()
    filters = JobBoardFilters(max_age_days=30, max_postings_per_run=1)
    result = await build(WorkingNomadsAdapter).collect(checkpoint("workingnomads", filters))
    assert len(result.postings) == 1
    assert result.truncated is True


@respx.mock
async def test_an_answer_that_is_not_a_list_is_an_invalid_payload() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=b'{"detail": "nope"}'))
    with pytest.raises(SourceError) as error:
        await build(WorkingNomadsAdapter).collect(checkpoint("workingnomads"))
    assert error.value.error_class is SourceErrorClass.INVALID_PAYLOAD


@respx.mock
async def test_validate_reports_the_matching_count() -> None:
    board()
    info = await build(WorkingNomadsAdapter).validate("workingnomads", scope=PORTUGAL)
    assert info.name == "Working Nomads"
    assert info.matching_count == 3


async def test_another_identifier_is_refused() -> None:
    with pytest.raises(SourceError):
        await build(WorkingNomadsAdapter).collect(checkpoint("jobicy"))


@respx.mock
async def test_the_page_slugs_come_from_one_lookup_for_the_ids_of_the_feed() -> None:
    board()
    result = await build(WorkingNomadsAdapter).collect(checkpoint("workingnomads"))
    assert [p.source_url for p in result.postings] == [
        PAGE + "senior-python-engineer-acme-systems-1000001",
        PAGE + "data-engineer-globex",
        PAGE + "platform-engineer-initech-1000003",
    ]
    (call,) = [c for c in respx.calls if c.request.url.path.endswith("/_search")]
    assert "1000001" in str(call.request.url) and "1000003" in str(call.request.url)


@respx.mock
async def test_a_failed_lookup_keeps_the_run_and_the_feed_address() -> None:
    """The slug is a courtesy: without it the posting keeps the feed address (apply redirect)."""
    board(search=httpx.Response(503))
    result = await build(WorkingNomadsAdapter).collect(checkpoint("workingnomads"))
    assert [p.company_name for p in result.postings] == ["Acme Systems", "Globex", "Initech"]
    assert all(p.source_url == p.external_job_id for p in result.postings)
