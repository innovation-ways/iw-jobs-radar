"""Pure rules that decide which job-board postings are kept (ADR-049.4)."""

from datetime import UTC, datetime, timedelta

import pytest

from jobs_radar.domain.job_board_rules import (
    UNKNOWN,
    WORLDWIDE,
    Eligibility,
    LocationPreference,
    LocationScope,
    Reach,
    allows_country,
    categorise,
    derive_location_scope,
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


PT = LocationScope(frozenset({"PT"}), include_worldwide=True)


@pytest.mark.parametrize(
    ("eligibility", "scope", "expected"),
    [
        (WORLDWIDE, PT, True),
        (WORLDWIDE, LocationScope(frozenset({"PT"}), include_worldwide=False), False),
        (UNKNOWN, LocationScope(frozenset({"PT"})), True),  # nothing stated: judged later
        (Eligibility(Reach.COUNTRIES, frozenset({"PT", "ES"})), PT, True),
        (Eligibility(Reach.COUNTRIES, frozenset({"US"})), PT, False),
        (Eligibility(Reach.COUNTRIES, frozenset({"US"})), LocationScope(any_country=True), True),
        (
            Eligibility(Reach.COUNTRIES, frozenset({"PT"})),
            LocationScope(include_worldwide=True),
            False,
        ),
    ],
)
def test_allows_country(eligibility: Eligibility, scope: LocationScope, expected: bool) -> None:
    assert allows_country(eligibility, scope) is expected


# --- location scope derived from the profile and the intents -------------------------------------


def pref(
    base: str | None = "PT",
    regions: tuple[str, ...] = ("PT",),
    *,
    remote: bool = True,
    local: bool = True,
) -> LocationPreference:
    return LocationPreference(base, regions, remote_acceptable=remote, local_acceptable=local)


def test_the_scope_is_the_base_country_plus_the_remote_regions() -> None:
    scope = derive_location_scope([pref("PT", ("EU",))])
    assert "PT" in scope.country_codes and "DE" in scope.country_codes
    assert scope.include_worldwide is True
    assert scope.any_country is False


def test_remote_work_from_anywhere_sets_any_country() -> None:
    assert derive_location_scope([pref("PT", ("WORLD",))]).any_country is True


def test_an_intent_that_rejects_remote_work_adds_no_remote_regions_or_worldwide() -> None:
    scope = derive_location_scope([pref("PT", ("EU",), remote=False)])
    assert scope == LocationScope(frozenset({"PT"}), include_worldwide=False)


def test_an_intent_that_rejects_local_work_adds_no_base_country() -> None:
    scope = derive_location_scope([pref("PT", ("ES",), local=False)])
    assert scope.country_codes == frozenset({"ES"})


def test_several_intents_are_combined() -> None:
    scope = derive_location_scope([pref("PT", ("ES",)), pref("PT", ("FR",), remote=True)])
    assert scope.country_codes == frozenset({"PT", "ES", "FR"})


def test_no_intent_or_nothing_acceptable_gives_an_empty_scope() -> None:
    assert derive_location_scope([]).is_empty
    assert derive_location_scope([pref(None, ("PT",), remote=False, local=True)]).is_empty


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
