"""dedup-v1: similarity, decisions and the primary-posting rule (document 13, section 10)."""

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jobs_radar.domain.dedup import (
    PrimaryCandidate,
    choose_primary,
    cosine,
    date_proximity,
    decide,
    jaccard,
    location_relation,
    shingles,
    similarity,
    title_similarity,
)

T0 = datetime(2026, 10, 1, tzinfo=UTC)


# --- title ---------------------------------------------------------------------------------------------


def test_titles_are_compared_as_token_sets_ignoring_case_order_and_punctuation() -> None:
    assert title_similarity("Senior AI Engineer", "senior ai engineer") == 1.0
    assert title_similarity("Senior AI Engineer", "AI Engineer, Senior") == 1.0
    assert title_similarity("Senior AI Engineer", "Senior AI Engineer (Remote)") == 1.0  # subset


def test_different_titles_score_low() -> None:
    assert title_similarity("Senior AI Engineer", "Account Executive") < 0.5


# --- description -----------------------------------------------------------------------------------------


def test_shingles_are_five_word_windows_of_normalised_text() -> None:
    result = shingles("One two three four five six")
    assert result == {
        ("one", "two", "three", "four", "five"),
        ("two", "three", "four", "five", "six"),
    }
    assert shingles("too short") == {("too", "short")}  # shorter than a window: one shingle
    assert shingles("") == frozenset()


def test_jaccard_measures_overlap() -> None:
    a = shingles("alpha beta gamma delta epsilon zeta eta theta")
    assert jaccard(a, a) == 1.0
    assert jaccard(a, shingles("totally different words appear in this other text")) == 0.0
    half = shingles("alpha beta gamma delta epsilon zeta")
    assert 0 < jaccard(a, half) < 1


def test_jaccard_of_empty_sets_is_zero() -> None:
    assert jaccard(frozenset(), frozenset()) == 0.0
    assert jaccard(shingles("a b c d e"), frozenset()) == 0.0


def test_cosine_of_embeddings() -> None:
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine([1.0, 1.0], [2.0, 2.0]) == pytest.approx(1.0)
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0  # no direction: no similarity


@given(
    st.lists(st.floats(-1, 1), min_size=1, max_size=6),
    st.lists(st.floats(-1, 1), min_size=1, max_size=6),
)
def test_cosine_stays_within_zero_and_one_for_any_vectors(u: list[float], v: list[float]) -> None:
    size = min(len(u), len(v))
    assert 0.0 <= cosine(u[:size], v[:size]) <= 1.0


# --- dates -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("days", "expected"),
    [(0, 1.0), (14, 1.0), (15, 0.5), (30, 0.5), (31, 0.0), (-10, 1.0)],
)
def test_date_proximity(days: int, expected: float) -> None:
    assert date_proximity(T0, T0 + timedelta(days=days)) == expected


def test_a_missing_date_gives_no_proximity() -> None:
    assert date_proximity(None, T0) == 0.0


# --- locations ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (["Lisbon, Portugal"], ["lisbon,  portugal"], "identical"),
        (["Lisbon", "Madrid"], ["Madrid", "Lisbon"], "identical"),
        (["Lisbon", "Madrid"], ["Madrid"], "overlap"),
        (["Lisbon"], ["Berlin"], "none"),
        (["Remote - EU"], ["Remote, EU"], "identical"),
        (["Remote"], ["Remote"], "identical"),
        (["Remote - EU"], ["Remote - Portugal"], "overlap"),  # Portugal is in the EU
        (["Remote - US"], ["Remote - EU"], "none"),
        ([], ["Lisbon"], "none"),
        (["Setúbal"], ["setubal"], "identical"),
    ],
)
def test_location_relation(a: list[str], b: list[str], expected: str) -> None:
    assert location_relation(a, b) == expected


# --- similarity and decisions ----------------------------------------------------------------------------------


def test_similarity_weights_the_four_parts() -> None:
    result = similarity(title=1.0, description=1.0, dates=1.0, location="identical")
    assert result.score == pytest.approx(1.0)
    only_title = similarity(title=1.0, description=0.0, dates=0.0, location="none")
    assert only_title.score == pytest.approx(0.35)
    mixed = similarity(title=0.8, description=0.9, dates=0.5, location="overlap")
    assert mixed.score == pytest.approx(0.35 * 0.8 + 0.45 * 0.9 + 0.10 * 0.5 + 0.10 * 0.5)
    assert mixed.features == {
        "title": 0.8,
        "description": 0.9,
        "dates": 0.5,
        "location": "overlap",
        "location_score": 0.5,
    }


@pytest.mark.parametrize(
    ("score", "location", "same_source", "expected"),
    [
        (0.95, "identical", False, "auto"),
        (0.90, "identical", False, "auto"),
        (0.95, "overlap", False, "possible"),  # auto needs an identical location
        (0.89, "identical", False, "possible"),
        (0.75, "overlap", False, "possible"),
        (0.74, "identical", False, "distinct"),
        (0.99, "none", False, "distinct"),  # different places are different opportunities
        (0.99, "identical", True, "possible"),  # same board: never auto
        (0.95, "identical", True, "possible"),
        (0.94, "identical", True, "distinct"),
    ],
)
def test_the_decision_table(score: float, location: str, same_source: bool, expected: str) -> None:
    assert decide(score, location, same_source=same_source) == expected


# --- primary posting ------------------------------------------------------------------------------------------------


def test_the_employers_own_ats_is_preferred_then_the_earliest_listing() -> None:
    candidates = [
        PrimaryCandidate(1, "aggregator", T0),
        PrimaryCandidate(2, "greenhouse", T0 + timedelta(days=2)),
        PrimaryCandidate(3, "greenhouse", T0 + timedelta(days=1)),
    ]
    assert choose_primary(candidates) == 3  # employer ATS, earliest of those
    assert choose_primary(candidates[:1]) == 1  # only an aggregator
    ties = [PrimaryCandidate(9, "lever", T0), PrimaryCandidate(4, "ashby", T0)]
    assert choose_primary(ties) == 4  # same time: lowest id, so the choice is reproducible


def test_a_job_board_listing_never_beats_the_company_board_as_primary() -> None:
    candidates = [
        PrimaryCandidate(1, "himalayas", T0),
        PrimaryCandidate(2, "arbeitnow", T0 + timedelta(days=1)),
        PrimaryCandidate(3, "greenhouse", T0 + timedelta(days=5)),
    ]
    assert choose_primary(candidates) == 3
