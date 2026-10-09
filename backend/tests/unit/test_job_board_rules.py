"""Pure rules that decide which job-board postings are kept (ADR-049.4)."""

from datetime import UTC, datetime, timedelta

import pytest

from jobs_radar.domain.job_board_rules import (
    UNKNOWN,
    WORLDWIDE,
    Eligibility,
    Reach,
    allows_country,
    categorise,
    eligibility_from_regions,
    is_recent,
    matches_terms,
)

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


# --- eligibility --------------------------------------------------------------------------------


@pytest.mark.parametrize("regions", [["Anywhere"], ["worldwide"], ["Global"], ["WORLD"]])
def test_worldwide_regions_are_worldwide(regions: list[str]) -> None:
    assert eligibility_from_regions(regions) == WORLDWIDE


def test_europe_expands_to_its_countries() -> None:
    eligibility = eligibility_from_regions(["Europe"])
    assert eligibility.reach is Reach.COUNTRIES
    assert {"PT", "DE", "GB"} <= eligibility.countries
    assert "US" not in eligibility.countries


def test_country_codes_and_groups_combine() -> None:
    eligibility = eligibility_from_regions(["US", "EU"])
    assert {"US", "PT"} <= eligibility.countries


def test_unrecognised_regions_are_unknown_not_rejected() -> None:
    assert eligibility_from_regions(["Somewhere nice"]) == UNKNOWN
    assert eligibility_from_regions([]) == UNKNOWN


@pytest.mark.parametrize(
    ("eligibility", "codes", "worldwide", "expected"),
    [
        (WORLDWIDE, ["PT"], True, True),
        (WORLDWIDE, ["PT"], False, False),
        (UNKNOWN, ["PT"], False, True),  # nothing stated: the later location judgement decides
        (Eligibility(Reach.COUNTRIES, frozenset({"PT", "ES"})), ["PT"], False, True),
        (Eligibility(Reach.COUNTRIES, frozenset({"US"})), ["PT"], True, False),
        (Eligibility(Reach.COUNTRIES, frozenset({"PT"})), [], True, False),
    ],
)
def test_allows_country(
    eligibility: Eligibility, codes: list[str], worldwide: bool, expected: bool
) -> None:
    assert allows_country(eligibility, codes, include_worldwide=worldwide) is expected


# --- categories ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        (["Senior Backend Engineer"], {"software"}),
        (["Full-Stack Developer", "React"], {"software"}),
        (["Data-Analyst"], {"data"}),
        (["Machine Learning Scientist"], {"data"}),
        (["Site Reliability Engineer"], {"devops", "software"}),
        (["DevOps / Cloud Platform"], {"devops"}),
        (["Application Security Engineer"], {"security", "software"}),
        (["Cybersecurity"], {"security"}),
        (["Marketing Manager", "Sales"], set()),
        (["Accountant"], set()),
    ],
)
def test_categorise_maps_titles_and_tags_to_areas(texts: list[str], expected: set[str]) -> None:
    assert categorise(texts) == expected


def test_categorise_does_not_match_inside_other_words() -> None:
    assert categorise(["Datasheet reviewer", "Safety officer"]) == set()


# --- age and terms ------------------------------------------------------------------------------


def test_recent_postings_and_postings_without_a_date_are_kept() -> None:
    assert is_recent(NOW - timedelta(days=29), NOW, 30)
    assert is_recent(None, NOW, 30)


def test_old_postings_are_dropped() -> None:
    assert not is_recent(NOW - timedelta(days=31), NOW, 30)


def test_no_search_terms_keeps_everything_and_terms_match_any_case() -> None:
    assert matches_terms("Rust developer", [])
    assert matches_terms("Rust developer", ["PYTHON", "rust"])
    assert not matches_terms("Java developer", ["python", "rust"])
