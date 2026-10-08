"""Registered-domain comparison used by the enrichment match rule (ADR-025)."""

import pytest

from jobs_radar.domain.domains import registered_domain


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.northwind.example/careers", "northwind.example"),
        ("http://northwind.example", "northwind.example"),
        ("https://jobs.eu.northwind.example/x?y=1", "northwind.example"),
        ("https://NorthWind.Example:8443/", "northwind.example"),
        ("https://www.northwind.co.uk/jobs", "northwind.co.uk"),
        ("northwind.example", "northwind.example"),
        ("www.northwind.example/path", "northwind.example"),
    ],
)
def test_the_registered_domain_ignores_subdomains_scheme_and_path(url: str, expected: str) -> None:
    assert registered_domain(url) == expected


@pytest.mark.parametrize(
    "url", ["", "   ", "not a url", "https://", "localhost", "http://127.0.0.1/x", "file:///etc"]
)
def test_values_without_a_real_domain_have_none(url: str) -> None:
    assert registered_domain(url) is None


def test_job_board_hosts_are_not_company_domains() -> None:
    from jobs_radar.domain.domains import is_job_board_host

    assert is_job_board_host("https://boards.greenhouse.io/acme")
    assert is_job_board_host("https://job-boards.greenhouse.io/acme/jobs/1")
    assert is_job_board_host("https://jobs.lever.co/acme")
    assert is_job_board_host("https://jobs.ashbyhq.com/acme")
    assert not is_job_board_host("https://www.northwind.example/careers")
