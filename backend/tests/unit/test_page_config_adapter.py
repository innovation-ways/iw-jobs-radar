"""The careers-page reader that executes an approved configuration (ADR-070 layer 3)."""

import pytest
import respx
from pydantic import ValidationError
from tests.job_board_support import ats_checkpoint, build_ats, payload

from jobs_radar.adapters.sources.base import SourceCheckpoint, SourceError
from jobs_radar.adapters.sources.page_config import (
    MAX_DETAIL_PAGES,
    PageConfigAdapter,
    extract_description,
    extract_listing,
)
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.schemas.page_reader import PageReaderConfig

HOST = "careers.synthco.example"
ORIGIN = f"https://{HOST}"
LISTING = f"{ORIGIN}/careers"


def config(**overrides: object) -> PageReaderConfig:
    base: dict[str, object] = {
        "listing_url": LISTING,
        "item_selector": "li.position",
        "title_selector": ".position-title",
        "link_selector": "a.position-link",
        "location_selector": ".position-place",
        "description_selector": ".role-body",
        "next_page_selector": "a.next",
        "fetch_detail": True,
        "max_pages": 3,
    }
    return PageReaderConfig.model_validate({**base, **overrides})


def checkpoint(cfg: PageReaderConfig) -> SourceCheckpoint:
    base = ats_checkpoint(HOST)
    return SourceCheckpoint(
        identifier=base.identifier,
        url=base.url,
        etag=None,
        rate_limit_per_minute=60,
        page_config=cfg.model_dump(mode="json"),
    )


def serve() -> None:
    respx.get(f"{ORIGIN}/robots.txt").respond(404)
    respx.get(LISTING, params={"page": "2"}).respond(
        200, content=payload("page_config", "listing_2.html")
    )
    respx.get(LISTING).respond(200, content=payload("page_config", "listing.html"))
    respx.get(f"{ORIGIN}/careers/roles/platform-engineer").respond(
        200, content=payload("page_config", "detail_platform.html")
    )
    respx.get(f"{ORIGIN}/careers/roles/data-analyst").respond(
        200, content=payload("page_config", "detail_data.html")
    )
    respx.get(f"{ORIGIN}/careers/roles/security-engineer").respond(404)


# --- the configuration -------------------------------------------------------------------------


def test_a_configuration_must_hold_valid_selectors() -> None:
    with pytest.raises(ValidationError):
        config(item_selector="li[")
    with pytest.raises(ValidationError):
        config(title_selector="   ")


def test_a_configuration_is_data_with_a_version() -> None:
    assert config().schema_version == 1
    with pytest.raises(ValidationError):
        PageReaderConfig.model_validate({**config().model_dump(), "run": "rm -rf /"})


# --- applying it to a page ---------------------------------------------------------------------


def test_the_listing_gives_title_address_and_place_of_each_posting_on_the_domain() -> None:
    html = payload("page_config", "listing.html").decode()
    postings, next_url = extract_listing(config(), html, LISTING)
    assert [(p.title, p.url, p.location) for p in postings] == [
        ("Platform Engineer", f"{ORIGIN}/careers/roles/platform-engineer", "Lisbon, Portugal"),
        ("Data Analyst", f"{ORIGIN}/careers/roles/data-analyst?src=site", "Remote - EU"),
    ]
    assert next_url == f"{ORIGIN}/careers?page=2"


def test_the_block_itself_is_the_link_when_no_link_selector_is_given() -> None:
    html = '<div class="r"><a class="r" href="/p/1">Role one</a><a class="r" href="/p/2">Role two</a></div>'
    cfg = config(
        item_selector="a.r", title_selector=None, link_selector=None, next_page_selector=None
    )
    postings, _ = extract_listing(cfg, html, LISTING)
    assert [p.title for p in postings] == ["Role one", "Role two"]
    assert postings[0].url == f"{ORIGIN}/p/1"


def test_the_description_is_the_configured_block_or_else_the_readable_page() -> None:
    detail = payload("page_config", "detail_platform.html").decode()
    assert "Run the synthetic platform." in extract_description(config(), detail)
    assert "Cookies and legal" not in extract_description(config(), detail)
    fallback = extract_description(config(description_selector=".missing"), detail)
    assert "Run the synthetic platform." in fallback


# --- collecting --------------------------------------------------------------------------------


@respx.mock
async def test_collect_follows_the_next_page_and_reads_each_posting_page() -> None:
    serve()
    result = await build_ats(PageConfigAdapter).collect(checkpoint(config()))
    titles = [p.title for p in result.postings]
    assert titles == ["Platform Engineer", "Data Analyst"]  # the third page entry is gone (404)
    first = result.postings[0]
    assert "Kubernetes" in first.description_text
    assert first.locations == ("Lisbon, Portugal",)
    assert result.declared_total == 3
    assert result.dropped_count == 1
    assert result.truncated is False


@respx.mock
async def test_without_detail_pages_only_the_listing_is_read() -> None:
    serve()
    result = await build_ats(PageConfigAdapter).collect(
        checkpoint(config(fetch_detail=False, next_page_selector=None))
    )
    assert [p.title for p in result.postings] == ["Platform Engineer", "Data Analyst"]
    assert not respx.get(f"{ORIGIN}/careers/roles/platform-engineer").called


@respx.mock
async def test_a_page_that_no_longer_matches_fails_as_schema_changed() -> None:
    serve()
    respx.get(LISTING).respond(200, html="<html><body><main>Redesigned</main></body></html>")
    with pytest.raises(SourceError) as caught:
        await build_ats(PageConfigAdapter).collect(checkpoint(config()))
    assert caught.value.error_class is SourceErrorClass.SCHEMA_CHANGED


@respx.mock
async def test_robots_txt_that_forbids_the_page_stops_the_source() -> None:
    respx.get(f"{ORIGIN}/robots.txt").respond(200, text="User-agent: *\nDisallow: /careers\n")
    with pytest.raises(SourceError) as caught:
        await build_ats(PageConfigAdapter).collect(checkpoint(config()))
    assert caught.value.error_class is SourceErrorClass.CONFIGURATION


async def test_a_source_without_a_configuration_cannot_run() -> None:
    with pytest.raises(SourceError) as caught:
        await build_ats(PageConfigAdapter).collect(ats_checkpoint(HOST))
    assert caught.value.error_class is SourceErrorClass.CONFIGURATION


@respx.mock
async def test_a_run_reads_at_most_the_detail_limit_and_is_then_partial() -> None:
    respx.get(f"{ORIGIN}/robots.txt").respond(404)
    items = "".join(
        f'<li class="position"><a class="position-link" href="/careers/roles/r{n}">'
        f'<span class="position-title">Role {n}</span></a></li>'
        for n in range(MAX_DETAIL_PAGES + 5)
    )
    respx.get(LISTING).respond(200, html=f"<main><ul>{items}</ul></main>")
    respx.get(url__regex=rf"{ORIGIN}/careers/roles/r\d+").respond(
        200, html="<main><div class='role-body'>Text</div></main>"
    )
    result = await build_ats(PageConfigAdapter).collect(
        checkpoint(config(next_page_selector=None, location_selector=None))
    )
    assert len(result.postings) == MAX_DETAIL_PAGES
    assert result.truncated is True


def test_the_type_and_the_endpoint() -> None:
    adapter = build_ats(PageConfigAdapter)
    assert adapter.source_type is SourceType.PAGE_CONFIG
    assert adapter.endpoint(f"{HOST}/careers") == LISTING
