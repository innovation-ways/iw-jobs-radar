"""Characterisation of ``matching-v1.8`` over fixed scenarios (ADR-080: C4).

Every scenario is a (job, intent, profile) triple built with the matching test builders. The golden file
records the score, band, recommendation, gates and every dimension. ADR-080 adds dimensions and a gate
that must leave all of this unchanged for existing intents (weight 0, gate off); phase 6b enables the
neutrality check (C5) on these same scenarios.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from tests.golden import check_golden, load_golden
from tests.unit.matching.builders import (
    BERLIN,
    DEFAULT_WEIGHTS,
    LISBON,
    SETUBAL,
    intent,
    job,
    pay,
    profile,
    remote_job,
    run,
    skills,
)

from jobs_radar.domain.matching.engine import evaluate
from jobs_radar.domain.matching.types import (
    DirectionJudgement,
    Evaluation,
    IntentView,
    JobAttributes,
    ProfileView,
    SkillRelations,
)


@dataclass(frozen=True)
class Scenario:
    """One named evaluation input."""

    job: JobAttributes
    intent: IntentView
    profile: ProfileView
    relations: SkillRelations


def _scenario(
    the_job: JobAttributes,
    the_intent: IntentView | None = None,
    the_profile: ProfileView | None = None,
    relations: SkillRelations | None = None,
) -> Scenario:
    return Scenario(the_job, the_intent or intent(), the_profile or profile(), relations or {})


_SENIOR_B2B = {
    "role_families": (("ai_solutions_engineering", 0.93),),
    "employment_types": ("contractor_b2b",),
    "seniority_levels": ("senior",),
    "sector_primary": "enterprise_it",
    "employer_type": "direct_employer",
}

SCENARIOS: dict[str, Callable[[], Scenario]] = {
    "remote_eu_preferred_everything": lambda: _scenario(
        remote_job(**_SENIOR_B2B, skills=skills((1, "must"), (2, "nice")))
    ),
    "remote_only_us_is_gated": lambda: _scenario(
        job(work_mode="remote", remote_regions=("US",), **_SENIOR_B2B)
    ),
    "remote_worldwide": lambda: _scenario(
        job(work_mode="remote", remote_regions=("WORLD",), **_SENIOR_B2B)
    ),
    "hybrid_inside_the_radius": lambda: _scenario(
        job(work_mode="hybrid", locations=(SETUBAL,), **_SENIOR_B2B)
    ),
    "onsite_outside_the_radius_is_gated": lambda: _scenario(
        job(work_mode="onsite", locations=(BERLIN,), **_SENIOR_B2B)
    ),
    "onsite_lisbon": lambda: _scenario(job(work_mode="onsite", locations=(LISBON,), **_SENIOR_B2B)),
    "rejected_role_family_is_gated": lambda: _scenario(
        remote_job(role_families=(("data_analysis", 0.9),), seniority_levels=("senior",))
    ),
    "unlisted_role_family_is_a_mismatch": lambda: _scenario(
        remote_job(role_families=(("qa_testing", 0.9),), seniority_levels=("senior",))
    ),
    "rejected_sector_is_gated": lambda: _scenario(
        remote_job(**{**_SENIOR_B2B, "sector_primary": "gambling"})
    ),
    "rejected_employer_type_is_gated": lambda: _scenario(
        remote_job(**{**_SENIOR_B2B, "employer_type": "consultancy_outsourcer"})
    ),
    "junior_is_gated": lambda: _scenario(remote_job(seniority_levels=("junior",))),
    "mid_to_senior_takes_the_best": lambda: _scenario(
        remote_job(seniority_levels=("mid", "senior"))
    ),
    "internship_is_gated": lambda: _scenario(remote_job(employment_types=("internship",))),
    "part_time_rejected_is_gated": lambda: _scenario(
        remote_job(employment_types=("employee_permanent",), hours="part_time")
    ),
    "contractor_day_rate_in_range": lambda: _scenario(
        remote_job(**_SENIOR_B2B, pay=pay("day_rate", 500, 550, "day"))
    ),
    "contractor_day_rate_below_minimum_is_gated": lambda: _scenario(
        remote_job(**_SENIOR_B2B, pay=pay("day_rate", 250, 300, "day"))
    ),
    "employee_salary_between_minimum_and_target": lambda: _scenario(
        remote_job(
            employment_types=("employee_permanent",),
            seniority_levels=("senior",),
            pay=pay("annual_salary", 65000, 70000, "year"),
        )
    ),
    "monthly_pay_is_converted_with_14_payments": lambda: _scenario(
        remote_job(
            employment_types=("employee_permanent",),
            pay=pay("annual_salary", 5000, 5000, "month"),
        )
    ),
    "pay_in_another_currency_is_unknown": lambda: _scenario(
        remote_job(
            employment_types=("employee_permanent",),
            pay=pay("annual_salary", 90000, 100000, "year", currency="USD"),
        )
    ),
    "skills_with_equivalents_and_gaps": lambda: _scenario(
        remote_job(
            **_SENIOR_B2B,
            skills=skills((1, "must"), (50, "must"), (51, "nice"), (99, "must")),
        ),
        relations={(50, 1): "equivalent", (51, 2): "related"},
    ),
    "required_language_not_spoken_is_gated": lambda: _scenario(
        remote_job(**_SENIOR_B2B, languages_required=("de",))
    ),
    "excluded_company_is_gated": lambda: _scenario(
        remote_job(**_SENIOR_B2B), intent(excluded_companies=("Acme",))
    ),
    "excluded_word_is_gated": lambda: _scenario(
        remote_job(**_SENIOR_B2B, description="This is an unpaid trial."),
        intent(excluded_words=("unpaid",)),
    ),
    "visa_not_offered_is_gated": lambda: _scenario(
        remote_job(**_SENIOR_B2B, visa_sponsorship=False), intent(needs_visa=True)
    ),
    "qualifications_weighted": lambda: _scenario(
        remote_job(**_SENIOR_B2B, education_required="msc"),
        intent(weights={**DEFAULT_WEIGHTS, "qualifications": 10}),
    ),
    "benefits_weighted": lambda: _scenario(
        remote_job(**_SENIOR_B2B, benefits_mentioned=("equity", "flexible_hours")),
        intent(
            benefits_wanted=("equity", "learning_budget"),
            weights={**DEFAULT_WEIGHTS, "benefits_flexibility": 10},
        ),
    ),
    "career_direction_strong": lambda: _scenario(
        remote_job(
            **_SENIOR_B2B,
            directions=(
                DirectionJudgement("Platforms", "strong", "build the platform", "my platform goal"),
            ),
        ),
        intent(weights={**DEFAULT_WEIGHTS, "career_direction": 10}),
    ),
    "career_direction_not_assessed": lambda: _scenario(
        remote_job(**_SENIOR_B2B, directions=None),
        intent(weights={**DEFAULT_WEIGHTS, "career_direction": 10}),
    ),
    "nothing_is_known": lambda: _scenario(job()),
}


def _describe(result: Evaluation) -> dict[str, Any]:
    """The parts of an evaluation that are persisted and shown, in a stable JSON shape."""
    return {
        "policy_version": result.policy_version,
        "fit_score": result.fit_score,
        "band": result.band,
        "recommendation": result.recommendation,
        "gates": [{"code": g.code, "reason": g.reason} for g in result.gates],
        "dimensions": [
            {
                "key": d.key,
                "status": d.status,
                "quality": d.quality,
                "weight": d.weight,
                "effective_weight": str(d.effective_weight),
                "strength": None if d.strength is None else str(d.strength),
                "contribution": str(d.contribution),
                "excluded": d.excluded,
            }
            for d in result.dimensions
        ],
    }


def test_there_are_enough_scenarios() -> None:
    assert len(SCENARIOS) >= 12


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_c4_each_scenario_is_deterministic(name: str) -> None:
    """The same inputs always give the same answer (the engine is a pure function)."""
    scenario = SCENARIOS[name]()
    first = evaluate(scenario.job, scenario.profile, scenario.intent, scenario.relations)
    second = evaluate(scenario.job, scenario.profile, scenario.intent, scenario.relations)
    assert _describe(first) == _describe(second)


def test_c4_matching_results_are_unchanged() -> None:
    results = {}
    for name in sorted(SCENARIOS):
        scenario = SCENARIOS[name]()
        results[name] = _describe(
            evaluate(scenario.job, scenario.profile, scenario.intent, scenario.relations)
        )
    check_golden("matching_scenarios", results)


def test_run_helper_is_the_same_engine() -> None:
    """Guards the builders: ``run`` is ``evaluate`` with defaults, so the scenarios mean what they say."""
    assert _describe(run()) == _describe(evaluate(job(), profile(), intent(), {}))


# --- C5: the new dimension changes no existing score (ADR-080, phase 6b) -----------------------------------


def test_c5_schedule_and_travel_change_no_existing_result() -> None:
    """The v1.8 golden is kept as it was. With the dimension for schedule and travel at weight 0
    (and the credential gate off), every scenario gives the same score, band, recommendation, gates
    and the same result for every other dimension. Only the policy version and the new, excluded
    dimension are new."""
    old = load_golden("matching_scenarios_v1_8")
    for name in sorted(SCENARIOS):
        scenario = SCENARIOS[name]()
        fresh = _describe(
            evaluate(scenario.job, scenario.profile, scenario.intent, scenario.relations)
        )
        new_dimensions = [d for d in fresh["dimensions"] if d["key"] == "schedule_travel"]
        for dimension in new_dimensions:
            assert dimension["excluded"] is True and dimension["weight"] == 0, name
            assert dimension["status"] == "unknown" and dimension["contribution"] == "0.0", name
        fresh["dimensions"] = [d for d in fresh["dimensions"] if d["key"] != "schedule_travel"]
        fresh["policy_version"] = old[name]["policy_version"]
        assert json.loads(json.dumps(fresh)) == old[name], name
