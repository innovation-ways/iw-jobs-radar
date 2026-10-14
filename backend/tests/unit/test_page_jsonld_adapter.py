"""The structured-postings adapter for a company's own careers site (ADR-070 layer 2)."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
import respx
from tests.job_board_support import Sleeper, ats_checkpoint, build_ats, payload

from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.adapters.sources.page_jsonld import (
    MAX_PAGES_PER_RUN,
    PageJsonLdAdapter,
    parse_job_posting,
)
from jobs_radar.domain.enums import SourceErrorClass, SourceType

HOST = "careers.synthco.example"
ORIGIN = f"https://{HOST}"
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def adapter(sleeper: Sleeper | None = None) -> PageJsonLdAdapter:
    return build_ats(PageJsonLdAdapter, sleeper, clock=lambda: NOW)


def serve(*, robots: str | None = None, index: bool = True) -> None:
    """A synthetic careers site: robots.txt, a sitemap index, one job sitemap and posting pages."""
    if robots is None:
        respx.get(f"{ORIGIN}/robots.txt").respond(
            200, text=f"User-agent: *\nDisallow: /search\nSitemap: {ORIGIN}/sitemap.xml\n"
        )
    else:
        respx.get(f"{ORIGIN}/robots.txt").respond(200, text=robots)
    respx.get(f"{ORIGIN}/sitemap.xml").respond(
        200,
        content=payload("page_jsonld", "sitemap_index.xml" if index else "sitemap_vacancies.xml"),
    )
    respx.get(f"{ORIGIN}/vacanciessitemap.xml").respond(
        200, content=payload("page_jsonld", "sitemap_vacancies.xml")
    )
    respx.get(f"{ORIGIN}/job/senior-platform-engineer-4052").respond(
        200, content=payload("page_jsonld", "posting_wise_like.html")
    )
    respx.get(f"{ORIGIN}/job/data-engineer-4053").respond(
        200, content=payload("page_jsonld", "posting_remote_graph.html")
    )
    respx.get(f"{ORIGIN}/job/closed-role-4000").respond(
        200, content=payload("page_jsonld", "posting_expired.html")
    )
    respx.get(f"{ORIGIN}/job/gone-4001").respond(404)


def test_the_type_and_the_endpoint() -> None:
    sut = adapter()
    assert sut.source_type is SourceType.PAGE_JSONLD
    assert sut.endpoint(HOST) == f"{ORIGIN}/"
    assert sut.endpoint(f"{HOST}/careers") == f"{ORIGIN}/careers"


# --- parsing one posting page ------------------------------------------------------------------


def test_a_job_posting_is_mapped_with_its_places_and_text() -> None:
    html = payload("page_jsonld", "posting_wise_like.html").decode()
    posting = parse_job_posting(html, f"{ORIGIN}/job/senior-platform-engineer-4052", NOW)
    assert posting is not None
    assert posting.title == "Senior Platform Engineer"
    assert posting.external_job_id == f"{ORIGIN}/job/senior-platform-engineer-4052"
    assert posting.source_url == posting.apply_url
    assert posting.locations == ("Lisbon, PT", "London, United Kingdom")
    assert posting.posted_at == datetime(2026, 10, 2, tzinfo=UTC)
    assert "Build the synthetic platform." in posting.description_text
    assert "- Python" in posting.description_text
    assert "<" not in posting.description_text


def test_a_telecommute_posting_in_a_graph_is_remote_in_the_named_country() -> None:
    html = payload("page_jsonld", "posting_remote_graph.html").decode()
    posting = parse_job_posting(html, f"{ORIGIN}/job/data-engineer-4053", NOW)
    assert posting is not None
    assert posting.locations == ("Remote - Portugal",)
    assert posting.posted_at == datetime(2026, 10, 5, 8, 30, tzinfo=UTC)


@pytest.mark.parametrize("name", ["posting_expired.html", "posting_none.html"])
def test_expired_or_absent_postings_are_not_postings(name: str) -> None:
    html = payload("page_jsonld", name).decode()
    assert parse_job_posting(html, f"{ORIGIN}/job/x", NOW) is None


# --- validating and collecting -----------------------------------------------------------------


@respx.mock
async def test_validate_counts_the_posting_pages_of_the_job_sitemap_only() -> None:
    serve()
    info = await adapter().validate(HOST)
    assert info.postings_count == 4  # the page of another domain is not counted
    assert info.name == "Synthco"


@respx.mock
async def test_validate_refuses_a_site_without_structured_postings() -> None:
    serve()
    for slug in ("senior-platform-engineer-4052", "data-engineer-4053", "closed-role-4000"):
        respx.get(f"{ORIGIN}/job/{slug}").respond(
            200, content=payload("page_jsonld", "posting_none.html")
        )
    with pytest.raises(SourceError) as caught:
        await adapter().validate(HOST)
    assert caught.value.error_class is SourceErrorClass.NOT_FOUND


@respx.mock
async def test_collect_returns_the_open_postings_newest_first() -> None:
    serve()
    result = await adapter().collect(ats_checkpoint(HOST))
    assert result.outcome == "modified"
    assert [p.title for p in result.postings] == ["Data Engineer", "Senior Platform Engineer"]
    assert result.dropped_count == 2  # the expired one and the one that is gone
    assert result.truncated is False
    assert result.etag


@respx.mock
async def test_an_unchanged_sitemap_means_nothing_changed_and_no_page_is_read() -> None:
    serve()
    first = await adapter().collect(ats_checkpoint(HOST))
    respx.reset()
    serve()
    pages = respx.get(f"{ORIGIN}/job/data-engineer-4053")
    second = await adapter().collect(ats_checkpoint(HOST, etag=first.etag))
    assert second.outcome == "not_modified"
    assert not pages.called


@respx.mock
async def test_robots_txt_that_forbids_the_site_stops_the_source() -> None:
    serve(robots="User-agent: *\nDisallow: /\n")
    with pytest.raises(SourceError) as caught:
        await adapter().collect(ats_checkpoint(HOST))
    assert caught.value.error_class is SourceErrorClass.CONFIGURATION
    assert "robots.txt" in caught.value.message


@respx.mock
async def test_a_failing_page_makes_the_run_partial_instead_of_failing_it() -> None:
    serve()
    respx.get(f"{ORIGIN}/job/data-engineer-4053").respond(503)
    result = await adapter().collect(ats_checkpoint(HOST))
    assert [p.title for p in result.postings] == ["Senior Platform Engineer"]
    assert result.truncated is True  # a posting could not be read, so none may be closed


@respx.mock
async def test_without_a_sitemap_the_links_of_the_careers_page_are_used() -> None:
    respx.get(f"{ORIGIN}/robots.txt").respond(404)
    respx.get(f"{ORIGIN}/sitemap.xml").respond(404)
    respx.get(f"{ORIGIN}/careers").respond(
        200,
        html='<a href="/job/data-engineer-4053">Data</a><a href="/about">About</a>'
        '<a href="https://elsewhere.example/job/x">Elsewhere</a>',
    )
    respx.get(f"{ORIGIN}/job/data-engineer-4053").respond(
        200, content=payload("page_jsonld", "posting_remote_graph.html")
    )
    result = await adapter().collect(ats_checkpoint(f"{HOST}/careers"))
    assert [p.title for p in result.postings] == ["Data Engineer"]


def _serve_many(count: int) -> None:
    """A site whose job sitemap lists ``count`` posting pages, all with the same posting."""
    respx.get(f"{ORIGIN}/robots.txt").respond(
        200, text=f"User-agent: *\nSitemap: {ORIGIN}/vacanciessitemap.xml\n"
    )
    urls = "".join(
        f"<url><loc>{ORIGIN}/job/role-{n}</loc><lastmod>2026-10-{1 + n % 9:02d}T00:00:00Z</lastmod></url>"
        for n in range(count)
    )
    respx.get(f"{ORIGIN}/vacanciessitemap.xml").respond(
        200,
        content=(
            '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{urls}</urlset>"
        ).encode(),
    )
    respx.get(url__regex=rf"{ORIGIN}/job/role-\d+").respond(
        200, content=payload("page_jsonld", "posting_wise_like.html")
    )


@respx.mock
async def test_a_normal_run_reads_at_most_the_page_limit_and_is_then_incomplete() -> None:
    _serve_many(MAX_PAGES_PER_RUN + 5)
    result = await adapter().collect(ats_checkpoint(HOST))
    assert len(result.postings) == MAX_PAGES_PER_RUN
    assert result.truncated is True
    assert result.etag is None


@respx.mock
async def test_the_first_run_of_a_source_reads_the_whole_backlog() -> None:
    _serve_many(MAX_PAGES_PER_RUN + 5)
    checkpoint = replace(ats_checkpoint(HOST), backlog=True)
    result = await adapter().collect(checkpoint)
    assert len(result.postings) == MAX_PAGES_PER_RUN + 5
    assert result.truncated is False
    assert result.etag is not None
