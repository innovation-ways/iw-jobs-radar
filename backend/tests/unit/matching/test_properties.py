"""Properties that must hold for any input (document 13, section 7; ADR-005, ADR-024)."""

from dataclasses import replace
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st
from tests.unit.matching.builders import BERLIN, LISBON, intent, job, pay, run

from jobs_radar.domain.matching.types import DIMENSION_KEYS, JobSkill

weights = st.fixed_dictionaries({key: st.integers(0, 40) for key in DIMENSION_KEYS}).filter(
    lambda w: sum(w.values()) > 0
)
modes = st.sampled_from([None, "remote", "hybrid", "onsite"])
regions = st.sampled_from([None, ("EU",), ("US",), ("UK", "PT")])
families = st.lists(
    st.tuples(
        st.sampled_from(["ai_solutions_engineering", "data_analysis", "other_role"]),
        st.floats(0, 1),
    ),
    max_size=3,
).map(tuple)
skill_sets = st.lists(
    st.tuples(st.integers(1, 5), st.sampled_from(["must", "nice"])),
    max_size=4,
    unique_by=lambda t: t[0],
).map(
    lambda items: tuple(JobSkill(i, f"s{i}", imp) for i, imp in items)  # type: ignore[arg-type]
)
pays = st.one_of(
    st.none(),
    st.builds(
        lambda low, spread: pay("annual_salary", low, low + spread, "year"),
        st.integers(20000, 120000),
        st.integers(0, 40000),
    ),
)
jobs = st.builds(
    lambda mode, reg, fam, sk, p, locs: job(
        work_mode=mode,
        remote_regions=reg,
        role_families=fam,
        skills=sk,
        pay=p,
        locations=locs,
        employment_types=("employee_permanent",) if p else None,
    ),
    modes,
    regions,
    families,
    skill_sets,
    pays,
    st.sampled_from([(), (LISBON,), (BERLIN,)]),
)


@settings(max_examples=150, deadline=None)
@given(jobs, weights)
def test_the_score_is_within_0_and_100_and_shares_add_up(the_job, the_weights) -> None:  # type: ignore[no-untyped-def]
    result = run(the_job, intent(weights=the_weights))
    assert 0 <= result.fit_score <= 100
    assert abs(sum(d.effective_weight for d in result.dimensions) - Decimal(100)) < Decimal("0.1")


@settings(max_examples=150, deadline=None)
@given(jobs, weights)
def test_a_zero_weight_is_excluded_and_contributes_nothing(the_job, the_weights) -> None:  # type: ignore[no-untyped-def]
    for d in run(the_job, intent(weights=the_weights)).dimensions:
        assert d.excluded == (d.weight == 0)
        if d.weight == 0:
            assert d.effective_weight == 0 and d.contribution == 0


@settings(max_examples=150, deadline=None)
@given(jobs, weights)
def test_unknown_and_mismatch_contribute_nothing_and_a_contribution_never_exceeds_the_share(
    the_job, the_weights
) -> None:  # type: ignore[no-untyped-def]
    for d in run(the_job, intent(weights=the_weights)).dimensions:
        if d.status in ("unknown", "mismatch"):
            assert d.contribution == 0
        assert d.contribution <= d.effective_weight + Decimal("0.05")


@settings(max_examples=100, deadline=None)
@given(jobs, weights)
def test_evaluation_is_deterministic(the_job, the_weights) -> None:  # type: ignore[no-untyped-def]
    assert run(the_job, intent(weights=the_weights)) == run(the_job, intent(weights=the_weights))


def outcome(evaluation):  # type: ignore[no-untyped-def]
    """What the score depends on; the order of evidence lists is presentation, not result."""
    return (
        evaluation.fit_score,
        evaluation.band,
        evaluation.recommendation,
        sorted(g.code for g in evaluation.gates),
        [(d.key, d.status, d.strength, d.contribution) for d in evaluation.dimensions],
    )


@settings(max_examples=100, deadline=None)
@given(jobs)
def test_the_order_of_options_does_not_change_the_result(the_job) -> None:  # type: ignore[no-untyped-def]
    base = intent()
    reordered = replace(
        base,
        stances={
            group: dict(reversed(list(options.items()))) for group, options in base.stances.items()
        },
    )
    reversed_job = replace(
        the_job,
        role_families=tuple(reversed(the_job.role_families)),
        skills=tuple(reversed(the_job.skills)),
    )
    assert (
        outcome(run(the_job, base))
        == outcome(run(the_job, reordered))
        == outcome(run(reversed_job, base))
    )


@settings(max_examples=100, deadline=None)
@given(jobs, weights)
def test_a_gate_always_means_not_recommended_and_the_other_way_round(the_job, the_weights) -> None:  # type: ignore[no-untyped-def]
    result = run(the_job, intent(weights=the_weights))
    assert (result.recommendation == "not_recommended") == bool(result.gates)
    assert (result.band == "not_recommended") == bool(result.gates)


@settings(max_examples=100, deadline=None)
@given(jobs)
def test_scaling_all_weights_does_not_change_the_score(the_job) -> None:  # type: ignore[no-untyped-def]
    even = dict.fromkeys(DIMENSION_KEYS, 0) | {
        "role_responsibilities": 20,
        "skills_technology": 10,
        "work_arrangement_location": 10,
        "engagement_terms": 10,
        "compensation": 10,
        "seniority_experience": 8,
        "domain_sector": 12,
        "company_profile": 6,
    }
    halved = {k: v // 2 for k, v in even.items()}  # weights are relative: only the shares matter
    assert (
        run(the_job, intent(weights=even)).fit_score
        == run(the_job, intent(weights=halved)).fit_score
    )
