"""Text helpers used to verify AI evidence and to truncate long descriptions."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jobs_radar.domain.text_match import normalise_for_match, quote_occurs, truncate_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Fully   remote\nwithin  EU ", "fully remote within eu"),
        ("It’s “great” – really", 'it\'s "great" - really'),  # curly quotes and dashes unified
        ("Ｆｕｌｌ　width", "full width"),  # compatibility characters
        ("", ""),
    ],
)
def test_normalisation_ignores_case_spacing_and_typographic_punctuation(
    raw: str, expected: str
) -> None:
    assert normalise_for_match(raw) == expected


def test_a_verbatim_quote_occurs_even_when_spacing_and_case_differ() -> None:
    text = "Design and evaluate\nLLM-powered   features for customers."
    assert quote_occurs("design and evaluate llm-powered features", text)


def test_a_quote_with_curly_quotes_matches_straight_quotes() -> None:
    assert quote_occurs("we're hiring", "We’re hiring now")


def test_a_paraphrase_does_not_occur() -> None:
    assert not quote_occurs("builds language model features", "Design and evaluate LLM features")


def test_an_empty_quote_never_counts_as_evidence() -> None:
    assert not quote_occurs("   ", "anything")
    assert not quote_occurs("", "")


def test_an_ellipsis_joins_fragments_that_each_must_occur() -> None:
    text = "Fully remote within EU time zones. We use Python daily."
    assert quote_occurs("Fully remote ... EU time zones", text)
    assert quote_occurs("Fully remote… Python", text)
    assert not quote_occurs("Fully remote ... Kubernetes", text)


def test_short_text_is_not_truncated() -> None:
    assert truncate_text("short text", 100) == ("short text", False)


def test_long_text_is_cut_at_a_word_boundary_and_flagged() -> None:
    text = "alpha beta gamma delta epsilon"
    cut, truncated = truncate_text(text, 14)
    assert truncated is True
    assert cut == "alpha beta"  # never cuts inside a word
    assert len(cut) <= 14


def test_text_without_spaces_is_cut_at_the_limit() -> None:
    cut, truncated = truncate_text("x" * 50, 20)
    assert (len(cut), truncated) == (20, True)


@given(st.text(max_size=300), st.integers(min_value=1, max_value=300))
def test_truncation_never_exceeds_the_limit_and_is_a_prefix(text: str, limit: int) -> None:
    cut, truncated = truncate_text(text, limit)
    assert len(cut) <= limit
    assert text.startswith(cut)
    assert truncated == (len(text) > limit)
