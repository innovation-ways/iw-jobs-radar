"""Eligibility read from the free-text location of a remote job board (ADR-074)."""

import pytest

from jobs_radar.adapters.sources.place_text import eligibility_from_place_text
from jobs_radar.domain.job_board_rules import Reach


@pytest.mark.parametrize("text", ["", "  ", "Global", "Worldwide", "Anywhere in the world"])
def test_empty_and_worldwide_words_mean_anyone(text: str) -> None:
    eligibility, places = eligibility_from_place_text(text)
    assert eligibility.reach is Reach.WORLDWIDE
    assert places == ("Worldwide",)


def test_named_countries_limit_the_work_to_them() -> None:
    eligibility, places = eligibility_from_place_text("Portugal, Spain")
    assert eligibility.reach is Reach.COUNTRIES
    assert {"PT", "ES"} <= eligibility.countries
    assert places == ("Portugal", "Spain")


def test_the_united_states_and_the_uk_are_read_by_their_short_names() -> None:
    assert eligibility_from_place_text("USA")[0].countries == frozenset({"US"})
    assert eligibility_from_place_text("UK")[0].countries == frozenset({"GB"})


def test_europe_names_the_european_countries() -> None:
    eligibility, _ = eligibility_from_place_text("Europe")
    assert eligibility.reach is Reach.COUNTRIES
    assert "PT" in eligibility.countries


def test_an_unreadable_part_keeps_the_posting_for_the_judgement() -> None:
    eligibility, _ = eligibility_from_place_text("Time zone: CET +/- 3 hours")
    assert eligibility.reach is Reach.UNKNOWN
    assert eligibility_from_place_text("Portugal, Moonbase Alpha")[0].reach is Reach.UNKNOWN
