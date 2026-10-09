"""Pure rules that decide which job-board postings are kept (ADR-049.4)."""

from datetime import UTC, datetime, timedelta

import pytest

from jobs_radar.domain.job_board_rules import (
    UNKNOWN,
    WORLDWIDE,
    Eligibility,
    LocationCandidate,
    LocationPreference,
    LocationScope,
    OnsiteArea,
    Reach,
    allows_country,
    allows_location,
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
        (["Site Reliability Engineer"], {"devops"}),
        (["DevOps / Cloud Platform"], {"devops"}),
        (["Application Security Engineer"], {"security"}),
        (["Cybersecurity"], {"security"}),
        (["Marketing Manager", "Sales"], set()),
        (["Solutions Engineer - Integration"], {"software"}),
        (["Database Engineer"], {"data"}),
        (["Lead AI Engineer"], {"data"}),
        (["Data Analytics Team Lead"], {"data"}),
        (["IT-Administrator Linux"], {"devops"}),
        (["Accountant"], set()),
        (["Hardware Engineer - Power Electronics"], set()),
        (["Freelance Senior Wind Engineer"], set()),
        (["Remote Field Application Scientist"], set()),
        (["Solar PV Field Testing Technician"], set()),
        (["Support Engineer"], set()),
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


@pytest.mark.parametrize(
    "title",
    [
        "Gujarati PDF Annotation Specialist",
        "Audio Transcription Specialist (Czech language)",
        "Dutch Linguistic Projects -- Sigma AI",
        "Ads Quality Rater - Dutch (Belgium)",
        "Online Data Analyst - German (AT)",
        "Slot Games Sound Designer Talent Pool",
        "Initiativbewerbung",
    ],
)
def test_data_labelling_gigs_and_talent_pools_have_no_area(title: str) -> None:
    assert categorise([title, "AI", "Data"]) == set()


# --- on-site work inside a radius -------------------------------------------------------------------

LISBON = OnsiteArea("Lisbon", 38.72, -9.14, 40)
PORTO = (41.15, -8.61)
SETUBAL = (38.52, -8.89)


def on_site(place: tuple[float, float] | None, *, remote: bool | None = False) -> LocationCandidate:
    return LocationCandidate(remote=remote, eligibility=UNKNOWN, place=place)


def scope_with_area() -> LocationScope:
    return LocationScope(frozenset({"PT"}), include_worldwide=True, onsite_areas=(LISBON,))


def test_an_on_site_posting_inside_the_radius_is_kept() -> None:
    assert allows_location(on_site(SETUBAL), scope_with_area())


def test_an_on_site_posting_outside_the_radius_is_dropped() -> None:
    assert not allows_location(on_site(PORTO), scope_with_area())


def test_an_on_site_posting_whose_place_is_unknown_is_kept_for_the_later_judgement() -> None:
    assert allows_location(on_site(None), scope_with_area())


def test_on_site_work_is_dropped_when_no_intent_accepts_it() -> None:
    scope = LocationScope(frozenset({"PT"}), include_worldwide=True)
    assert not allows_location(on_site(SETUBAL), scope)


def test_a_remote_posting_follows_the_country_rules_not_the_radius() -> None:
    candidate = LocationCandidate(remote=True, eligibility=WORLDWIDE, place=PORTO)
    assert allows_location(candidate, scope_with_area())
    far = LocationCandidate(
        remote=True, eligibility=Eligibility(Reach.COUNTRIES, frozenset({"US"})), place=None
    )
    assert not allows_location(far, scope_with_area())


def test_the_scope_collects_the_radius_of_each_intent_that_accepts_local_work() -> None:
    preference = LocationPreference("PT", ("PT",), True, True, onsite_area=LISBON)
    assert derive_location_scope([preference]).onsite_areas == (LISBON,)
    rejects = LocationPreference("PT", ("PT",), True, False, onsite_area=LISBON)
    assert derive_location_scope([rejects]).onsite_areas == ()
