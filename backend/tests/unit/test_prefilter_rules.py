"""Pre-filter rules built from keywords (ADR-080, phase 5): safe by construction, no regex typed."""

import pytest

from jobs_radar.domain.prefilter import Area, PrefilterRules

ELECTRICAL = Area("electrical", "Electrical", ("electrician", "wiring", "switch board"))
PLUMBING = Area("plumbing", "Plumbing", ("plumber", "pipefitter", "gas fitt*"))


def rules(*, noise: tuple[str, ...] = ()) -> PrefilterRules:
    return PrefilterRules((ELECTRICAL, PLUMBING), noise)


def test_a_title_belongs_to_the_areas_whose_keywords_it_contains() -> None:
    assert rules().categorise(["Maintenance Electrician"]) == {"electrical"}
    assert rules().categorise(["Plumber and electrician"]) == {"electrical", "plumbing"}
    assert rules().categorise(["Accountant"]) == frozenset()


def test_keywords_match_whole_words_only() -> None:
    assert rules().categorise(["Electrician's helper"]) == {"electrical"}
    assert (
        rules().categorise(["Electricians wanted"]) == frozenset()
    )  # a plural needs its own keyword
    assert rules().categorise(["Plumbers"]) == frozenset()


def test_case_and_separators_do_not_matter() -> None:
    assert rules().categorise(["ELECTRICIAN"]) == {"electrical"}
    assert rules().categorise(["switch-board_wiring/install"]) == {"electrical"}
    assert rules().categorise(["switch   board"]) == {"electrical"}


def test_a_star_makes_a_keyword_match_any_ending() -> None:
    assert rules().categorise(["Gas fitter"]) == {"plumbing"}
    assert rules().categorise(["Gas fitting engineer"]) == {"plumbing"}
    assert rules().categorise(["Gas"]) == frozenset()


def test_titles_tags_and_categories_are_read_together() -> None:
    assert rules().categorise(["Technician", "wiring", "Construction"]) == {"electrical"}


def test_a_noise_word_rules_the_whole_posting_out() -> None:
    noisy = rules(noise=("volunteer*", "unpaid"))
    assert noisy.categorise(["Volunteering electrician"]) == frozenset()
    assert noisy.categorise(["Unpaid trial plumber"]) == frozenset()
    assert noisy.categorise(["Electrician"]) == {"electrical"}


def test_special_characters_in_keywords_are_text_not_patterns() -> None:
    odd = PrefilterRules((Area("c", "C family", ("c++", "c#", "node.js")),), ())
    assert odd.categorise(["C++ developer"]) == {"c"}
    assert odd.categorise(["Senior C# engineer"]) == {"c"}
    assert odd.categorise(["Node.js"]) == {"c"}
    assert odd.categorise(["c"]) == frozenset()  # "c++" is not the bare letter


def test_hostile_input_is_harmless_and_fast() -> None:
    text = "a" * 20000 + " " + "(" * 500
    assert rules().categorise([text]) == frozenset()


def test_the_rules_list_their_areas_and_have_an_empty_form() -> None:
    assert [a.key for a in rules().areas] == ["electrical", "plumbing"]
    assert PrefilterRules.empty().areas == ()
    assert PrefilterRules.empty().categorise(["Electrician"]) == frozenset()


def test_areas_with_the_same_key_are_merged() -> None:
    """Two packs that both define ``electrical`` give one area with the keywords of both."""
    merged = PrefilterRules.merged(
        [
            PrefilterRules((Area("electrical", "Electrical", ("electrician",)),), ("unpaid",)),
            PrefilterRules((Area("electrical", "Electric work", ("lineman",)),), ("unpaid", "gig")),
        ]
    )
    assert [(a.key, a.label) for a in merged.areas] == [("electrical", "Electrical")]
    assert merged.categorise(["Lineman"]) == {"electrical"}
    assert merged.noise == ("unpaid", "gig")


@pytest.mark.parametrize("bad", ["", "  ", "*", "a(b", "x[y]", "back\\slash", "a|b"])
def test_a_keyword_with_pattern_characters_is_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="keyword"):
        PrefilterRules((Area("x", "X", (bad,)),), ())
