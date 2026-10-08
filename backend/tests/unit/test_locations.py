"""Offline place lookup with the disambiguation rules of document 13, section 6.2."""

import pytest

from jobs_radar.domain.geo import haversine_km
from jobs_radar.services.locations import Gazetteer, load_gazetteer


@pytest.fixture(scope="module")
def gazetteer() -> Gazetteer:
    return load_gazetteer()


def test_a_unique_city_is_resolved_with_country_timezone_and_coordinates(
    gazetteer: Gazetteer,
) -> None:
    place = gazetteer.resolve("Lisbon")
    assert place is not None
    assert (place.city, place.country, place.timezone) == ("Lisbon", "PT", "Europe/Lisbon")
    assert place.label == "Lisbon, Portugal"
    assert place.latitude == pytest.approx(38.725, abs=0.01)


@pytest.mark.parametrize(
    "text", ["Lisboa", "LISBON", "Lisbon, Portugal", "Lisbon, PT", "Lisbon (Hybrid)"]
)
def test_spellings_countries_and_decorations_resolve_to_the_same_city(
    gazetteer: Gazetteer, text: str
) -> None:
    place = gazetteer.resolve(text)
    assert place is not None and (place.city, place.country) == ("Lisbon", "PT")


def test_accents_do_not_matter_and_setubal_is_within_40_km_of_lisbon(gazetteer: Gazetteer) -> None:
    lisbon, setubal = gazetteer.resolve("Lisbon"), gazetteer.resolve("Setubal")
    assert lisbon is not None and setubal is not None
    assert setubal.city == "Setúbal"
    assert haversine_km(lisbon.latitude, lisbon.longitude, setubal.latitude, setubal.longitude) < 40


def test_a_name_in_several_countries_is_unresolved_without_a_country(gazetteer: Gazetteer) -> None:
    assert gazetteer.resolve("Oeiras") is None  # Portugal and Brazil


@pytest.mark.parametrize(
    ("text", "hint", "country"),
    [
        ("Oeiras, Portugal", None, "PT"),
        ("Oeiras, PT", None, "PT"),
        ("Oeiras", "PT", "PT"),
        ("Oeiras", "BR", "BR"),
        ("Oeiras, Brazil", None, "BR"),
    ],
)
def test_a_country_resolves_the_ambiguity(
    gazetteer: Gazetteer, text: str, hint: str | None, country: str
) -> None:
    place = gazetteer.resolve(text, country=hint)
    assert place is not None and place.country == country


def test_a_country_hint_without_a_match_in_that_country_is_unresolved(gazetteer: Gazetteer) -> None:
    assert gazetteer.resolve("Lisbon", country="BR") is None


def test_the_same_name_in_one_country_picks_the_most_populous(gazetteer: Gazetteer) -> None:
    place = gazetteer.resolve("Springfield")  # many in the US only
    assert place is not None and place.country == "US" and place.population > 150_000


def test_an_exact_primary_name_beats_alternate_names_elsewhere(gazetteer: Gazetteer) -> None:
    place = gazetteer.resolve("Berlin")
    assert place is not None and place.country == "DE"


@pytest.mark.parametrize("text", ["", "   ", "Remote - EU", "Xyzzyville", "Nowhereville, Portugal"])
def test_unknown_and_non_place_text_is_unresolved(gazetteer: Gazetteer, text: str) -> None:
    assert gazetteer.resolve(text) is None


def test_search_ranks_by_population_and_filters_by_country(gazetteer: Gazetteer) -> None:
    results = gazetteer.search("lisb", limit=5)
    assert results and results[0].city == "Lisbon"
    assert len(results) <= 5
    only_pt = gazetteer.search("oei", country="PT")
    assert only_pt and {p.country for p in only_pt} == {"PT"}
    assert gazetteer.search("") == [] and gazetteer.search("zzzzzz") == []


def test_a_small_injected_gazetteer_follows_the_same_rules() -> None:
    cities = [
        {
            "geonameid": 1,
            "name": "Alpha",
            "latitude": 1.0,
            "longitude": 1.0,
            "countrycode": "XX",
            "population": 100,
            "timezone": "UTC",
            "alternatenames": [],
        },
        {
            "geonameid": 2,
            "name": "Alpha",
            "latitude": 2.0,
            "longitude": 2.0,
            "countrycode": "XX",
            "population": 900,
            "timezone": "UTC",
            "alternatenames": [],
        },
        {
            "geonameid": 3,
            "name": "Beta",
            "latitude": 3.0,
            "longitude": 3.0,
            "countrycode": "XX",
            "population": 5,
            "timezone": "UTC",
            "alternatenames": ["Alpha"],
        },
        {
            "geonameid": 4,
            "name": "Gamma",
            "latitude": 4.0,
            "longitude": 4.0,
            "countrycode": "XX",
            "population": 5,
            "timezone": "UTC",
            "alternatenames": [],
        },
        {
            "geonameid": 5,
            "name": "Gamma",
            "latitude": 5.0,
            "longitude": 5.0,
            "countrycode": "YY",
            "population": 7,
            "timezone": "UTC",
            "alternatenames": [],
        },
    ]
    small = Gazetteer(cities, {"XX": "Xland", "YY": "Yland"})
    alpha = small.resolve("Alpha")
    assert (
        alpha is not None and alpha.latitude == 2.0
    )  # most populous exact match; alt name ignored
    assert small.resolve("Gamma") is None  # two countries, no hint
    gamma = small.resolve("Gamma, Yland")
    assert gamma is not None and gamma.country == "YY"
    beta = small.resolve("Beta")
    assert beta is not None and beta.city == "Beta"
