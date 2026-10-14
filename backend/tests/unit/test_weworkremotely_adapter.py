"""The We Work Remotely adapter against recorded synthetic feeds (ADR-072, research R-00173)."""

import httpx
import pytest
import respx
from tests.job_board_support import PORTUGAL, build, checkpoint, payload

from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.adapters.sources.weworkremotely import FEEDS, WeWorkRemotelyAdapter
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters

BASE = "https://weworkremotely.com/"
GUID = BASE + "remote-jobs/"
PROGRAMMING = "categories/remote-full-stack-programming-jobs.rss"


def route_feeds(main: bytes, programming: bytes, other: bytes) -> list[respx.Route]:
    """Mock every feed: the main one, one category feed with ``programming``, the rest ``other``."""
    routes = []
    for path in FEEDS:
        body = main if path == "remote-jobs.rss" else programming if path == PROGRAMMING else other
        routes.append(respx.get(BASE + path).mock(return_value=httpx.Response(200, content=body)))
    return routes


def feeds_ok() -> list[respx.Route]:
    return route_feeds(
        payload("weworkremotely", "remote-jobs.rss"),
        payload("weworkremotely", "programming.rss"),
        payload("weworkremotely", "empty.rss"),
    )


def test_the_adapter_is_a_catalogue_job_board() -> None:
    assert WeWorkRemotelyAdapter.source_type is SourceType.WEWORKREMOTELY
    assert WeWorkRemotelyAdapter.entry.catalogue_key == "weworkremotely"
    assert "remote-jobs.rss" in FEEDS and len(FEEDS) == len(set(FEEDS))


@respx.mock
async def test_collect_reads_every_feed_once_and_filters() -> None:
    routes = feeds_ok()
    result = await build(WeWorkRemotelyAdapter).collect(checkpoint("weworkremotely"))
    assert all(route.call_count == 1 for route in routes)
    assert [p.external_job_id for p in result.postings] == [
        GUID + "acme-senior-backend-engineer",
        GUID + "globex-data-engineer",
        GUID + "soylent-devops-engineer",
    ]
    # Sales role, US-only role, 38-day-old role, a posting without company, Americas-only role.
    assert result.dropped_count == 5
    assert result.truncated is False
    assert result.outcome == "modified"


@respx.mock
async def test_a_posting_is_mapped_with_company_title_places_and_date() -> None:
    feeds_ok()
    result = await build(WeWorkRemotelyAdapter).collect(checkpoint("weworkremotely"))
    acme, globex, soylent = result.postings
    assert acme.company_name == "Acme Robotics"
    assert acme.title == "Senior Backend Engineer"
    assert acme.source_url == acme.apply_url == GUID + "acme-senior-backend-engineer"
    assert acme.locations == ("Worldwide",)
    assert acme.departments == ("Back-End Programming",)
    assert acme.posted_at is not None and acme.posted_at.isoformat() == "2026-10-08T09:00:00+00:00"
    assert "Synthetic description" in acme.description_text
    assert "<" not in acme.description_text
    # Country names with flags are read into plain names.
    assert globex.locations == ("Portugal", "Spain", "Germany")
    assert soylent.locations == ("Europe",)


@respx.mock
async def test_without_worldwide_only_postings_naming_the_owner_countries_pass() -> None:
    feeds_ok()
    scope = LocationScope(frozenset({"PT"}), include_worldwide=False)
    result = await build(WeWorkRemotelyAdapter).collect(checkpoint("weworkremotely", scope=scope))
    assert [p.company_name for p in result.postings] == ["Globex", "Soylent"]


@respx.mock
async def test_search_terms_and_categories_are_applied() -> None:
    feeds_ok()
    filters = JobBoardFilters(categories=["devops"], max_age_days=30)
    result = await build(WeWorkRemotelyAdapter).collect(checkpoint("weworkremotely", filters))
    assert [p.company_name for p in result.postings] == ["Soylent"]


@respx.mock
async def test_the_per_run_limit_truncates_the_run() -> None:
    feeds_ok()
    filters = JobBoardFilters(max_age_days=30, max_postings_per_run=1)
    result = await build(WeWorkRemotelyAdapter).collect(checkpoint("weworkremotely", filters))
    assert len(result.postings) == 1
    assert result.truncated is True


@respx.mock
async def test_a_page_that_is_not_a_feed_is_an_invalid_payload() -> None:
    route_feeds(
        payload("weworkremotely", "not_a_feed.html"),
        payload("weworkremotely", "empty.rss"),
        payload("weworkremotely", "empty.rss"),
    )
    with pytest.raises(SourceError) as error:
        await build(WeWorkRemotelyAdapter).collect(checkpoint("weworkremotely"))
    assert error.value.error_class is SourceErrorClass.INVALID_PAYLOAD


@respx.mock
async def test_a_blocked_feed_is_an_authentication_error() -> None:
    for path in FEEDS:
        respx.get(BASE + path).mock(return_value=httpx.Response(403, content=b"blocked"))
    with pytest.raises(SourceError) as error:
        await build(WeWorkRemotelyAdapter).collect(checkpoint("weworkremotely"))
    assert error.value.error_class is SourceErrorClass.AUTHENTICATION


@respx.mock
async def test_validate_reports_the_matching_count() -> None:
    feeds_ok()
    info = await build(WeWorkRemotelyAdapter).validate("weworkremotely", scope=PORTUGAL)
    assert info.name == "We Work Remotely"
    assert info.matching_count == 3


async def test_another_identifier_is_refused() -> None:
    with pytest.raises(SourceError):
        await build(WeWorkRemotelyAdapter).collect(checkpoint("jobicy"))
