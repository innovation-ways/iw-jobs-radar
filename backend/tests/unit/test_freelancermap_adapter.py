"""The freelancermap adapter against recorded synthetic pages (ADR-075, research R-00176)."""

import httpx
import pytest
import respx
from tests.job_board_support import PORTUGAL, build, checkpoint, payload

from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.adapters.sources.freelancermap import FreelancermapAdapter
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters

BASE = "https://www.freelancermap.com"
PAGES = [
    "senior-data-engineer-1001",
    "billing-consultant-1002",
    "devops-engineer-london-1003",
    "archived-qa-engineer-1005",
    "permanent-architect-1006",
    "sales-manager-1007",
]


def site(robots: bytes | None = None) -> dict[str, respx.Route]:
    """Mock the sitemap, robots.txt and every project page; return the page routes by slug."""
    respx.get(f"{BASE}/robots.txt").mock(
        return_value=httpx.Response(200, content=robots or payload("freelancermap", "robots.txt"))
    )
    respx.get(f"{BASE}/sitemaps/projects.xml").mock(
        return_value=httpx.Response(200, content=payload("freelancermap", "projects.xml"))
    )
    respx.get(f"{BASE}/sitemaps/projects-0.xml").mock(
        return_value=httpx.Response(200, content=payload("freelancermap", "projects-0.xml"))
    )
    return {
        slug: respx.get(f"{BASE}/project/{slug}").mock(
            return_value=httpx.Response(200, content=payload("freelancermap", f"{slug}.html"))
        )
        for slug in PAGES
    }


def test_the_adapter_is_a_catalogue_job_board() -> None:
    assert FreelancermapAdapter.source_type is SourceType.FREELANCERMAP
    assert FreelancermapAdapter.entry.catalogue_key == "freelancermap"


@respx.mock
async def test_collect_reads_recent_pages_and_filters() -> None:
    routes = site()
    result = await build(FreelancermapAdapter).collect(
        checkpoint("freelancermap", JobBoardFilters(max_age_days=30))
    )
    assert [p.external_job_id for p in result.postings] == ["1001", "1002", "1006"]
    # The London on-site role, the archived role and the sales role; the 2026-06 entry is never read.
    assert result.dropped_count == 3
    assert all(route.call_count == 1 for route in routes.values())
    assert result.truncated is False


@respx.mock
async def test_a_posting_states_the_contract_type_remote_share_and_skills() -> None:
    site()
    result = await build(FreelancermapAdapter).collect(
        checkpoint("freelancermap", JobBoardFilters(max_age_days=30))
    )
    freelance, agency, permanent = result.postings
    assert freelance.company_name == "Acme Talent GmbH"
    assert freelance.source_url == f"{BASE}/project/senior-data-engineer-1001"
    assert freelance.description_text.startswith("Contract type: Freelance")
    assert "Remote: 100%" in freelance.description_text
    assert "Duration: 6 months" in freelance.description_text
    assert "Skills: Python, SQL" in freelance.description_text
    assert "Day rate EUR 600" in freelance.description_text
    assert freelance.locations == ("Warsaw, Poland", "Remote")
    assert freelance.posted_at is not None and freelance.posted_at.year == 2026
    assert "Contract type: Agency contract" in agency.description_text
    assert "Remote: 60%" in agency.description_text
    assert "Contract type: Permanent" in permanent.description_text


@respx.mock
async def test_only_the_newest_pages_are_read_within_the_page_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routes = site()
    monkeypatch.setattr("jobs_radar.adapters.sources.freelancermap.MAX_PAGES_PER_RUN", 2)
    result = await build(FreelancermapAdapter).collect(
        checkpoint("freelancermap", JobBoardFilters(max_age_days=30))
    )
    read = [slug for slug, route in routes.items() if route.call_count]
    assert read == ["senior-data-engineer-1001", "billing-consultant-1002"]
    # The cap cut the list, so the run says it did not see everything.
    assert result.truncated is True


@respx.mock
async def test_a_site_whose_robots_txt_refuses_is_not_read() -> None:
    routes = site(robots=b"User-agent: *\nDisallow: /\n")
    with pytest.raises(SourceError) as error:
        await build(FreelancermapAdapter).collect(
            checkpoint("freelancermap", JobBoardFilters(max_age_days=30))
        )
    assert error.value.error_class is SourceErrorClass.CONFIGURATION
    assert all(route.call_count == 0 for route in routes.values())


@respx.mock
async def test_pages_that_no_longer_match_fail_as_schema_changed() -> None:
    site()
    for slug in PAGES:
        respx.get(f"{BASE}/project/{slug}").mock(
            return_value=httpx.Response(200, content=payload("freelancermap", "not_a_project.html"))
        )
    with pytest.raises(SourceError) as error:
        await build(FreelancermapAdapter).collect(
            checkpoint("freelancermap", JobBoardFilters(max_age_days=30))
        )
    assert error.value.error_class is SourceErrorClass.SCHEMA_CHANGED


@respx.mock
async def test_validate_reports_the_matching_count() -> None:
    site()
    info = await build(FreelancermapAdapter).validate(
        "freelancermap", filters=JobBoardFilters(max_age_days=30), scope=PORTUGAL
    )
    assert info.name == "freelancermap"
    assert info.matching_count == 3


@respx.mock
async def test_without_on_site_areas_hybrid_roles_are_left_out() -> None:
    site()
    scope = LocationScope(frozenset({"PT"}), include_worldwide=True)
    result = await build(FreelancermapAdapter).collect(
        checkpoint("freelancermap", JobBoardFilters(max_age_days=30), scope)
    )
    assert [p.external_job_id for p in result.postings] == ["1001", "1006"]


async def test_another_identifier_is_refused() -> None:
    with pytest.raises(SourceError):
        await build(FreelancermapAdapter).collect(checkpoint("jobicy"))
