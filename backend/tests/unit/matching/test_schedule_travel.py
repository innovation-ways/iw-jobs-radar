"""Working patterns and travel: the schedule_travel dimension and gates G13 and G14 (ADR-080, 6b)."""

from decimal import Decimal

from tests.unit.matching.builders import DEFAULT_WEIGHTS, dim, gate_codes, intent, job, run

from jobs_radar.domain.matching.types import DimensionResult, IntentView, JobAttributes

WEIGHTS = {**DEFAULT_WEIGHTS, "schedule_travel": 10}


def with_stances(
    schedules: dict[str, str] | None = None, travel: dict[str, str] | None = None
) -> IntentView:
    base = intent(weights=WEIGHTS)
    stances = {**base.stances}
    if schedules is not None:
        stances["schedules"] = schedules  # type: ignore[assignment]
    if travel is not None:
        stances["travel_levels"] = travel  # type: ignore[assignment]
    return intent(weights=WEIGHTS, stances=stances)


def result(the_job: JobAttributes, the_intent: IntentView) -> DimensionResult:
    return dim(run(the_job, the_intent), "schedule_travel")


def test_without_either_the_dimension_is_unknown() -> None:
    assert result(job(), with_stances({"day": "preferred"})).status == "unknown"


def test_a_preferred_working_pattern_is_a_full_match_and_an_acceptable_one_half() -> None:
    stances = with_stances({"day": "preferred", "night": "acceptable"})
    assert result(job(schedules=("day",)), stances).strength == Decimal("1.0000")
    assert result(job(schedules=("night",)), stances).strength == Decimal("0.5000")


def test_a_job_that_offers_several_patterns_takes_the_best_one() -> None:
    stances = with_stances({"day": "preferred", "night": "rejected"})
    pair = run(job(schedules=("day", "night")), stances)
    assert dim(pair, "schedule_travel").strength == Decimal("1.0000")
    assert gate_codes(pair) == []  # not every pattern is rejected


def test_when_every_pattern_offered_is_rejected_g13_fires() -> None:
    stances = with_stances({"day": "acceptable", "night": "rejected", "weekends": "rejected"})
    outcome = run(
        job(schedules=("night", "weekends"), evidence={"schedule": "nights and weekends"}), stances
    )
    assert gate_codes(outcome) == ["G13"]
    (gate,) = outcome.gates
    assert gate.evidence["job_quote"] == "nights and weekends"
    assert outcome.recommendation == "not_recommended"


def test_travel_has_its_own_stances_and_gate() -> None:
    stances = with_stances(
        travel={"none": "preferred", "occasional": "acceptable", "frequent": "rejected"}
    )
    assert result(job(travel="none"), stances).strength == Decimal("1.0000")
    assert result(job(travel="occasional"), stances).strength == Decimal("0.5000")
    frequent = run(job(travel="frequent", evidence={"travel": "travel 4 days a week"}), stances)
    assert gate_codes(frequent) == ["G14"]
    assert frequent.gates[0].evidence["job_quote"] == "travel 4 days a week"


def test_the_weaker_of_the_two_counts_when_both_are_stated() -> None:
    stances = with_stances(
        {"day": "preferred"},
        {"none": "preferred", "occasional": "acceptable", "frequent": "rejected"},
    )
    assert result(job(schedules=("day",), travel="occasional"), stances).strength == Decimal(
        "0.5000"
    )


def test_one_stated_part_is_enough() -> None:
    stances = with_stances({"day": "preferred"}, {"occasional": "acceptable"})
    assert result(job(schedules=("day",)), stances).strength == Decimal("1.0000")
    assert result(job(travel="occasional"), stances).strength == Decimal("0.5000")


def test_a_pattern_the_intent_does_not_list_is_a_mismatch_without_a_gate() -> None:
    outcome = run(job(schedules=("on_call",)), with_stances({"day": "preferred"}))
    assert dim(outcome, "schedule_travel").status == "mismatch"
    assert gate_codes(outcome) == []


def test_gates_fire_even_when_the_dimension_has_no_weight() -> None:
    no_weight = intent(
        stances={**intent().stances, "schedules": {"night": "rejected", "day": "acceptable"}}
    )
    outcome = run(job(schedules=("night",)), no_weight)
    assert dim(outcome, "schedule_travel").excluded is True
    assert gate_codes(outcome) == ["G13"]


def test_a_gate_never_fires_on_unknown_data() -> None:
    stances = with_stances(
        {"night": "rejected", "day": "acceptable"}, {"frequent": "rejected", "none": "acceptable"}
    )
    assert gate_codes(run(job(), stances)) == []


def test_the_scoring_arithmetic_uses_the_weight() -> None:
    """A weight of 10 on a strength of 1 adds its share of the total (10 of 110)."""
    outcome = run(job(schedules=("day",)), with_stances({"day": "preferred"}))
    assert dim(outcome, "schedule_travel").effective_weight == Decimal("9.09")


def test_the_policy_is_the_one_that_has_this_dimension() -> None:
    assert run().policy_version == "matching-v1.9"
