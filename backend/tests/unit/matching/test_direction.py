"""The career-direction dimension (ADR-057): the best judged direction counts, decided by code."""

from decimal import Decimal

import pytest
from tests.unit.matching.builders import DEFAULT_WEIGHTS, dim, gate_codes, intent, job, run

from jobs_radar.domain.matching.types import DIMENSION_KEYS, DirectionJudgement

KEY = "career_direction"


def judged(label: str, level: str, quote: str | None = "Billing platform") -> DirectionJudgement:
    return DirectionJudgement(
        label=label,
        level=level,  # type: ignore[arg-type]
        job_quote=quote,
        direction_quote="billing SME",
    )


def weighted(weight: int = 15):  # type: ignore[no-untyped-def]
    return intent(weights={**DEFAULT_WEIGHTS, KEY: weight})


def test_the_dimension_exists_and_is_optional() -> None:
    assert KEY in DIMENSION_KEYS
    result = dim(run(), KEY)
    assert result.excluded is True and result.weight == 0  # no weight: left out, like benefits


@pytest.mark.parametrize(
    ("level", "strength", "status", "quality"),
    [
        ("strong", "1.0000", "match", "strong"),
        ("partial", "0.5000", "match", "partial"),
        ("weak", "0.2000", "match", "weak"),
        ("none", "0.0000", "mismatch", None),
    ],
)
def test_a_judged_level_gives_its_fixed_strength(
    level: str, strength: str, status: str, quality: str | None
) -> None:
    result = dim(run(job(directions=(judged("Billing SME", level),)), weighted()), KEY)
    assert (result.status, result.strength, result.quality) == (
        status,
        Decimal(strength),
        quality,
    )


def test_the_best_direction_counts_and_is_named() -> None:
    directions = (judged("AI engineer", "weak"), judged("Billing SME", "strong"))
    result = dim(run(job(directions=directions), weighted()), KEY)
    assert (result.status, result.strength) == ("match", Decimal("1.0000"))
    assert result.evidence["direction"] == "Billing SME"
    assert result.evidence["job_quote"] == "Billing platform"
    assert result.evidence["direction_quote"] == "billing SME"


def test_a_fit_in_only_one_of_two_directions_is_still_a_strong_fit() -> None:
    both = run(job(directions=(judged("A", "strong"), judged("B", "none"))), weighted())
    only = run(job(directions=(judged("A", "strong"),)), weighted())
    assert dim(both, KEY).strength == dim(only, KEY).strength == Decimal("1.0000")
    assert both.fit_score == only.fit_score


def test_unknown_judgements_count_as_zero_but_keep_the_weight() -> None:
    result = run(job(directions=(judged("A", "unknown", None),)), weighted())
    found = dim(result, KEY)
    assert (found.status, found.contribution, found.excluded) == ("unknown", Decimal("0.0"), False)
    assert found.effective_weight == Decimal("13.04")  # 15 of 115


def test_a_known_level_beats_an_unknown_one() -> None:
    directions = (judged("A", "unknown", None), judged("B", "partial"))
    assert dim(run(job(directions=directions), weighted()), KEY).strength == Decimal("0.5000")


def test_a_job_that_was_not_assessed_leaves_the_dimension_out() -> None:
    # No judgement at all: the weight does not count, so the others keep their shares.
    without = run(job(), intent())
    not_assessed = run(job(directions=None), weighted())
    found = dim(not_assessed, KEY)
    assert found.excluded is True and found.weight == 0 and found.effective_weight == 0
    assert not_assessed.fit_score == without.fit_score
    assert [d.effective_weight for d in not_assessed.dimensions if d.key != KEY] == [
        d.effective_weight for d in without.dimensions if d.key != KEY
    ]


def test_without_a_weight_a_judged_job_scores_as_before() -> None:
    plain = run(job(), intent())
    judged_job = run(job(directions=(judged("A", "strong"),)), intent())
    assert judged_job.fit_score == plain.fit_score
    assert dim(judged_job, KEY).excluded is True


def test_a_direction_never_fires_a_gate() -> None:
    result = run(job(directions=(judged("A", "none"),)), weighted())
    assert gate_codes(result) == []


def test_a_strong_direction_adds_its_share_of_the_score() -> None:
    base = run(job(), weighted())
    strong = run(job(directions=(judged("A", "strong"),)), weighted())
    assert dim(strong, KEY).contribution == Decimal("13.0")  # 15 of 115, rounded to one decimal
    assert strong.fit_score >= base.fit_score
