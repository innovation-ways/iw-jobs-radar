"""Golden examples of document 13, section 7.7, plus scoring arithmetic and bands."""

from decimal import Decimal

import pytest
from tests.unit.matching.builders import DEFAULT_WEIGHTS, dim, gate_codes, intent, job, profile, run

from jobs_radar.domain.matching.engine import evaluate
from jobs_radar.domain.matching.types import JobSkill


def worked_example_job():  # type: ignore[no-untyped-def]
    """Strengths: role 1.0, skills 0.8, arrangement 1.0, engagement 1.0, pay unknown,
    seniority 1.0, sector 0.5, company 1.0 (document 13, section 7.7)."""
    return job(
        role_families=(("ai_solutions_engineering", 0.93),),
        # must (weight 2) covered, must equivalent (0.5), nice (weight 1) covered: (2 + 1 + 1) / 5
        skills=(
            JobSkill(1, "Python", "must"),
            JobSkill(50, "Postgres", "must"),
            JobSkill(2, "Kubernetes", "nice"),
        ),
        work_mode="remote",
        remote_regions=("EU",),
        employment_types=("contractor_b2b",),
        seniority_levels=("senior",),
        sector_primary="enterprise_it",
        employer_type="direct_employer",
    )


RELATIONS = {(50, 1): "equivalent", (50, 2): "equivalent"}


def test_the_default_weights_give_82_excellent() -> None:
    result = evaluate(worked_example_job(), profile(), intent(), RELATIONS)
    contributions = {d.key: d.contribution for d in result.dimensions}
    assert contributions == {
        "role_responsibilities": Decimal("25.0"),
        "skills_technology": Decimal("12.0"),
        "work_arrangement_location": Decimal("15.0"),
        "engagement_terms": Decimal("10.0"),
        "compensation": Decimal("0.0"),
        "seniority_experience": Decimal("8.0"),
        "domain_sector": Decimal("5.0"),
        "company_profile": Decimal("7.0"),
        "benefits_flexibility": Decimal("0.0"),
        "qualifications": Decimal("0.0"),
    }
    assert result.fit_score == 82
    assert (result.band, result.recommendation, result.gates) == ("excellent", "recommended", ())
    assert dim(result, "compensation").status == "unknown"


def test_raising_the_compensation_weight_to_30_gives_68() -> None:
    weights = {**DEFAULT_WEIGHTS, "compensation": 30}
    result = evaluate(worked_example_job(), profile(), intent(weights=weights), RELATIONS)
    assert result.fit_score == 68
    assert result.band == "strong"
    assert dim(result, "compensation").effective_weight == Decimal("25")  # 30 of 120
    assert dim(result, "compensation").contribution == Decimal("0.0")  # unknown adds nothing


def test_the_policy_version_is_recorded() -> None:
    assert run().policy_version == "matching-v1"


def test_a_job_with_nothing_known_scores_zero_and_is_still_recommended() -> None:
    result = run(job())
    assert result.fit_score == 0 and result.band == "low"
    assert result.gates == () and result.recommendation == "recommended"
    assert all(d.status == "unknown" for d in result.dimensions)


@pytest.mark.parametrize(
    ("score_target_weights", "band"),
    [
        ({"role_responsibilities": 100}, "excellent"),  # strength 1.0 -> 100
        ({"role_responsibilities": 4, "skills_technology": 1}, "excellent"),  # 80
    ],
)
def test_bands_follow_the_thresholds(score_target_weights: dict[str, int], band: str) -> None:
    weights = dict.fromkeys(DEFAULT_WEIGHTS, 0) | score_target_weights
    result = run(
        job(
            role_families=(("ai_solutions_engineering", 0.9),),
            skills=(JobSkill(1, "Python", "must"),),
        ),
        intent(weights=weights),
    )
    assert result.band == band


@pytest.mark.parametrize(
    ("preferred_weight", "other_weight", "score", "band"),
    [
        (79, 21, 79, "strong"),  # 79 of 100 earned with strength 1 on 79, 0 on the rest
        (80, 20, 80, "excellent"),
        (65, 35, 65, "strong"),
        (64, 36, 64, "average"),
        (45, 55, 45, "average"),
        (44, 56, 44, "low"),
    ],
)
def test_band_boundaries(preferred_weight: int, other_weight: int, score: int, band: str) -> None:
    # role scores 1.0 and skills score 0.0 (a missing must-have), so score = role share.
    weights = dict.fromkeys(DEFAULT_WEIGHTS, 0)
    weights["role_responsibilities"] = preferred_weight
    weights["skills_technology"] = other_weight
    result = run(
        job(
            role_families=(("ai_solutions_engineering", 0.9),),
            skills=(JobSkill(99, "Unheld", "must"),),
        ),
        intent(weights=weights),
    )
    assert (result.fit_score, result.band) == (score, band)


def test_a_gate_overrides_the_band_but_the_raw_score_is_still_shown() -> None:
    result = run(
        job(
            role_families=(("ai_solutions_engineering", 0.9),),
            description="This role is unpaid.",
        ),
        intent(excluded_words=("unpaid",)),
    )
    assert gate_codes(result) == ["G9"]
    assert result.recommendation == "not_recommended" and result.band == "not_recommended"
    assert result.fit_score > 0


def test_contributions_use_one_decimal_with_half_up_rounding() -> None:
    # 1 of 8 weight on a strength of 0.5 -> 6.25 -> 6.3 (half up), not 6.2 (banker's rounding)
    weights = dict.fromkeys(DEFAULT_WEIGHTS, 0) | {
        "role_responsibilities": 1,
        "skills_technology": 7,
    }
    result = run(
        job(role_families=(("software_engineering_general", 0.9),)),
        intent(weights=weights),
    )
    assert dim(result, "role_responsibilities").contribution == Decimal("6.3")


def test_all_weights_zero_is_rejected() -> None:
    with pytest.raises(ValueError, match="weight"):
        run(job(), intent(weights=dict.fromkeys(DEFAULT_WEIGHTS, 0)))
