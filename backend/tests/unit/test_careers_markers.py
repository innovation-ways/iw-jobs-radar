"""Finding an applicant tracking system in a careers address or page (ADR-070.2)."""

import pytest

from jobs_radar.domain.careers_markers import (
    AtsMatch,
    ats_in_address,
    ats_in_html,
    looks_script_only,
    normalise_https_address,
)
from jobs_radar.domain.enums import SourceType

# --- the address alone -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("https://boards.greenhouse.io/datadog", (SourceType.GREENHOUSE, "datadog")),
        ("https://job-boards.greenhouse.io/datadog/jobs/123", (SourceType.GREENHOUSE, "datadog")),
        ("https://boards.eu.greenhouse.io/acme", (SourceType.GREENHOUSE, "acme")),
        ("https://boards-api.greenhouse.io/v1/boards/acme/jobs", (SourceType.GREENHOUSE, "acme")),
        ("https://jobs.lever.co/acme-labs", (SourceType.LEVER, "acme-labs")),
        ("https://jobs.eu.lever.co/acme", (SourceType.LEVER, "acme")),
        ("https://jobs.ashbyhq.com/mistral.ai", (SourceType.ASHBY, "mistral.ai")),
        ("https://jobs.ashbyhq.com/acme/6fa1-22", (SourceType.ASHBY, "acme")),
        ("https://careers.smartrecruiters.com/Acme", (SourceType.SMARTRECRUITERS, "Acme")),
        ("https://jobs.smartrecruiters.com/AcmeInc/743", (SourceType.SMARTRECRUITERS, "AcmeInc")),
    ],
)
def test_known_board_addresses_give_the_type_and_identifier(
    address: str, expected: tuple[SourceType, str]
) -> None:
    assert ats_in_address(address) == AtsMatch(*expected)


@pytest.mark.parametrize(
    "address",
    [
        "https://example.com/careers",
        "https://boards.greenhouse.io/",
        "https://boards.greenhouse.io/embed/job_board",
        "https://notgreenhouse.io/acme",
        "https://example.com/?next=https://jobs.lever.co/acme",
    ],
)
def test_an_address_that_is_not_a_board_gives_nothing(address: str) -> None:
    assert ats_in_address(address) is None


# --- the page ----------------------------------------------------------------------------------


def test_an_embedded_greenhouse_board_is_found_in_the_page() -> None:
    html = '<script src="https://boards.greenhouse.io/embed/job_board/js?for=datadog"></script>'
    assert ats_in_html(html) == [AtsMatch(SourceType.GREENHOUSE, "datadog")]


def test_links_to_several_systems_are_all_reported_once_in_page_order() -> None:
    html = """
      <a href="https://jobs.lever.co/acme/1">One</a>
      <a href="https://jobs.lever.co/acme/2">Two</a>
      <iframe src="https://job-boards.greenhouse.io/acmelabs"></iframe>
      <a href="https://jobs.ashbyhq.com/acme.io">Three</a>
    """
    assert ats_in_html(html) == [
        AtsMatch(SourceType.LEVER, "acme"),
        AtsMatch(SourceType.GREENHOUSE, "acmelabs"),
        AtsMatch(SourceType.ASHBY, "acme.io"),
    ]


def test_the_public_api_addresses_are_recognised_too() -> None:
    html = (
        "fetch('https://api.lever.co/v0/postings/acme?mode=json');"
        "fetch('https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensation=true');"
        "fetch('https://api.smartrecruiters.com/v1/companies/AcmeInc/postings');"
    )
    assert ats_in_html(html) == [
        AtsMatch(SourceType.LEVER, "acme"),
        AtsMatch(SourceType.ASHBY, "acme"),
        AtsMatch(SourceType.SMARTRECRUITERS, "AcmeInc"),
    ]


def test_reserved_path_words_are_not_identifiers() -> None:
    html = '<a href="https://boards.greenhouse.io/embed/job_app?token=1">Apply</a>'
    assert ats_in_html(html) == []


def test_a_page_without_markers_gives_nothing() -> None:
    assert ats_in_html("<html><body><a href='/jobs'>Jobs</a></body></html>") == []


def test_eightfold_is_signalled_by_its_assets_not_by_an_identifier() -> None:
    from jobs_radar.domain.careers_markers import mentions_eightfold

    assert mentions_eightfold('<script src="https://static.vscdn.net/js/app.js"></script>')
    assert mentions_eightfold("Powered by eightfold.ai")
    assert not mentions_eightfold("<html></html>")


# --- script-only pages -------------------------------------------------------------------------


def test_an_application_shell_with_no_content_is_script_only() -> None:
    html = '<html><body><div id="__nuxt"></div><script src="/app.js"></script></body></html>'
    assert looks_script_only(html)


def test_a_page_with_posting_like_links_is_not_script_only() -> None:
    html = '<div id="root"></div><a href="/jobs/senior-engineer-123">Senior engineer</a>'
    assert not looks_script_only(html)


def test_a_static_page_with_plenty_of_text_is_not_script_only() -> None:
    html = "<html><body><p>" + "word " * 120 + "</p></body></html>"
    assert not looks_script_only(html)


def test_a_server_rendered_shell_without_posting_links_is_still_script_only() -> None:
    html = (
        '<div id="__nuxt"><nav>' + "menu entry " * 80 + '</nav><a href="/vacancies">All</a></div>'
    )
    assert looks_script_only(html)


# --- normalising what the owner typed ----------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("https://Wise.jobs/", "https://wise.jobs/"),
        ("wise.jobs", "https://wise.jobs/"),
        ("http://example.com/careers/", "https://example.com/careers/"),
        ("https://example.com/careers?lang=en#top", "https://example.com/careers?lang=en"),
    ],
)
def test_addresses_are_normalised_to_https(typed: str, expected: str) -> None:
    assert normalise_https_address(typed) == expected


@pytest.mark.parametrize(
    "typed",
    [
        "",
        "not a url",
        "ftp://example.com",
        "https://localhost/jobs",
        "https://192.168.0.10/jobs",
        "https://user:secret@example.com/",
        "javascript:alert(1)",
    ],
)
def test_addresses_that_are_not_public_websites_are_refused(typed: str) -> None:
    assert normalise_https_address(typed) is None


# --- the identifier of a careers page ----------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "identifier"),
    [
        ("https://Wise.jobs/", "wise.jobs"),
        ("https://example.com/careers/?lang=en", "example.com/careers"),
        ("https://careers.example.com/en/jobs", "careers.example.com/en/jobs"),
    ],
)
def test_a_careers_page_identifier_round_trips_to_its_address(
    address: str, identifier: str
) -> None:
    from jobs_radar.domain.careers_markers import page_address, page_identifier

    assert page_identifier(address) == identifier
    assert page_address(identifier).startswith(f"https://{identifier}")
