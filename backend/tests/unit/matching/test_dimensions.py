"""One test per dimension rule of document 13, section 7.4 and 7.5."""

from decimal import Decimal

import pytest
from tests.unit.matching.builders import (
    BERLIN,
    LISBON,
    SETUBAL,
    dim,
    gate_codes,
    intent,
    job,
    pay,
    profile,
    remote_job,
    run,
    skills,
)

from jobs_radar.domain.matching.types import JobLocation, JobSkill

# --- role & responsibilities -----------------------------------------------------------------------

ROLE = "role_responsibilities"


@pytest.mark.parametrize(
    ("family", "strength", "quality"),
    [
        ("ai_solutions_engineering", "1.0000", "strong"),  # preferred
        ("software_engineering_general", "0.5000", "partial"),  # acceptable
    ],
)
def test_role_strength_follows_the_stance(family: str, strength: str, quality: str) -> None:
    result = dim(run(job(role_families=((family, 0.9),))), ROLE)
    assert (result.status, result.strength, result.quality) == ("match", Decimal(strength), quality)


def test_role_families_below_the_confidence_floor_are_ignored() -> None:
    result = dim(run(job(role_families=(("ai_solutions_engineering", 0.59),))), ROLE)
    assert result.status == "unknown"


def test_no_role_family_is_unknown() -> None:
    assert dim(run(job()), ROLE).status == "unknown"


def test_the_best_role_family_counts_and_a_rejected_secondary_one_does_not_gate() -> None:
    evaluation = run(job(role_families=(("ai_solutions_engineering", 0.9), ("data_analysis", 0.9))))
    assert dim(evaluation, ROLE).strength == Decimal("1.0000")
    assert "G1" not in gate_codes(evaluation)


def test_a_rejected_primary_role_family_fires_g1_even_with_an_acceptable_secondary_one() -> None:
    # The first family is the one that best fits the role (a "Sales Engineer" listed as sales
    # first and consulting second is still a sales job).
    evaluation = run(job(role_families=(("data_analysis", 0.9), ("ai_solutions_engineering", 0.9))))
    assert gate_codes(evaluation) == ["G1"]
    assert dim(evaluation, ROLE).status == "mismatch"


def test_the_primary_role_family_is_the_first_one_that_clears_the_confidence_floor() -> None:
    evaluation = run(job(role_families=(("data_analysis", 0.5), ("ai_solutions_engineering", 0.9))))
    assert "G1" not in gate_codes(evaluation)


def test_an_unlisted_role_family_is_a_mismatch_without_a_gate() -> None:
    evaluation = run(job(role_families=(("product_management", 0.9),)))
    assert (dim(evaluation, ROLE).status, dim(evaluation, ROLE).strength) == (
        "mismatch",
        Decimal("0.0000"),
    )
    assert "G1" not in gate_codes(evaluation)


def test_when_every_identified_role_family_is_rejected_gate_g1_fires() -> None:
    evaluation = run(job(role_families=(("data_analysis", 0.9),)))
    assert gate_codes(evaluation) == ["G1"]
    assert dim(evaluation, ROLE).status == "mismatch"


# --- skills & technology -----------------------------------------------------------------------------

SKILLS = "skills_technology"


def test_skills_held_by_the_profile_cover_fully() -> None:
    result = dim(run(job(skills=skills((1, "must"), (2, "must")))), SKILLS)
    assert (result.status, result.strength) == ("match", Decimal("1.0000"))


def test_must_skills_weigh_twice_as_much_as_nice_ones() -> None:
    # must held (2) and nice missing (1): 2 / 3
    result = dim(run(job(skills=skills((1, "must"), (99, "nice")))), SKILLS)
    assert result.strength == Decimal("0.6667")
    # must missing (2) and nice held (1): 1 / 3
    result = dim(run(job(skills=skills((99, "must"), (1, "nice")))), SKILLS)
    assert result.strength == Decimal("0.3333")


def test_an_equivalent_skill_covers_half_and_a_related_one_a_quarter() -> None:
    equivalent = dim(
        run(job(skills=skills((50, "must"))), relations={(50, 1): "equivalent"}), SKILLS
    )
    assert equivalent.strength == Decimal("0.5000")
    related = dim(run(job(skills=skills((50, "must"))), relations={(50, 2): "related"}), SKILLS)
    assert related.strength == Decimal("0.2500")
    both = dim(
        run(
            job(skills=skills((50, "must"))), relations={(50, 2): "related", (50, 1): "equivalent"}
        ),
        SKILLS,
    )
    assert both.strength == Decimal("0.5000")  # the best relation wins


def test_unjudged_or_unrelated_skills_cover_nothing_and_a_missing_must_is_not_a_gate() -> None:
    evaluation = run(job(skills=skills((99, "must"))), relations={(99, 1): "unrelated"})
    assert (dim(evaluation, SKILLS).status, dim(evaluation, SKILLS).strength) == (
        "mismatch",
        Decimal("0.0000"),
    )
    assert gate_codes(evaluation) == []


def test_no_skills_is_unknown() -> None:
    assert dim(run(job()), SKILLS).status == "unknown"


# --- work arrangement & location ------------------------------------------------------------------

WORK = "work_arrangement_location"


def test_remote_in_an_eligible_region_scores_the_mode_stance() -> None:
    assert dim(run(remote_job()), WORK).strength == Decimal("1.0000")  # remote is preferred
    acceptable = intent(
        stances={
            **intent().stances,
            "work_arrangements": {
                "remote": "acceptable",
                "hybrid": "acceptable",
                "onsite": "acceptable",
            },
        }
    )
    assert dim(run(remote_job(), acceptable), WORK).strength == Decimal("0.5000")


@pytest.mark.parametrize("regions", [None, ("Atlantis",)])
def test_remote_with_unstated_or_unrecognised_regions_is_a_risk_not_a_mismatch(
    regions: tuple[str, ...] | None,
) -> None:
    evaluation = run(job(work_mode="remote", remote_regions=regions))
    assert dim(evaluation, WORK).strength == Decimal("0.8000")
    assert gate_codes(evaluation) == []


def test_remote_restricted_to_other_regions_fires_g2() -> None:
    evaluation = run(job(work_mode="remote", remote_regions=("US",)))
    assert gate_codes(evaluation) == ["G2"]
    assert dim(evaluation, WORK).status == "mismatch"


def test_a_rejected_arrangement_fires_g2() -> None:
    rejecting = intent(
        stances={
            **intent().stances,
            "work_arrangements": {
                "remote": "preferred",
                "hybrid": "acceptable",
                "onsite": "rejected",
            },
        }
    )
    evaluation = run(job(work_mode="onsite", locations=(LISBON,)), rejecting)
    assert gate_codes(evaluation) == ["G2"]


def test_an_unknown_mode_is_unknown() -> None:
    assert dim(run(job()), WORK).status == "unknown"


def test_hybrid_within_the_radius_scores_the_stance_and_setubal_is_close_enough() -> None:
    near = dim(run(job(work_mode="hybrid", locations=(SETUBAL,))), WORK)
    assert (near.status, near.strength) == ("match", Decimal("0.5000"))  # hybrid is acceptable
    assert any(item["km"] < 40 for item in near.evidence["locations"])


def test_hybrid_outside_the_radius_fires_g2() -> None:
    evaluation = run(job(work_mode="hybrid", locations=(BERLIN,)))
    assert gate_codes(evaluation) == ["G2"]


def test_one_location_within_the_radius_is_enough() -> None:
    evaluation = run(job(work_mode="onsite", locations=(BERLIN, LISBON)))
    assert dim(evaluation, WORK).status == "match" and gate_codes(evaluation) == []


def test_unplaced_locations_make_the_dimension_unknown_without_a_gate() -> None:
    evaluation = run(job(work_mode="hybrid", locations=(JobLocation("Somewhere small"),)))
    assert dim(evaluation, WORK).status == "unknown" and gate_codes(evaluation) == []
    assert dim(run(job(work_mode="hybrid")), WORK).status == "unknown"


# --- engagement & contract terms ---------------------------------------------------------------------

ENGAGEMENT = "engagement_terms"


def test_the_best_engagement_type_counts() -> None:
    result = dim(run(job(employment_types=("employee_permanent", "contractor_b2b"))), ENGAGEMENT)
    assert result.strength == Decimal("1.0000")


def test_all_engagement_types_rejected_fires_g3() -> None:
    assert gate_codes(run(job(employment_types=("internship",)))) == ["G3"]


def test_part_time_is_limited_by_the_part_time_stance() -> None:
    acceptable = intent(part_time="acceptable")
    result = dim(
        run(job(employment_types=("contractor_b2b",), hours="part_time"), acceptable), ENGAGEMENT
    )
    assert result.strength == Decimal("0.5000")
    preferred = intent(part_time="preferred")
    assert dim(
        run(job(employment_types=("contractor_b2b",), hours="part_time"), preferred), ENGAGEMENT
    ).strength == Decimal("1.0000")


def test_part_time_when_part_time_is_rejected_fires_g3() -> None:
    evaluation = run(
        job(employment_types=("contractor_b2b",), hours="part_time")
    )  # builder rejects part-time
    assert gate_codes(evaluation) == ["G3"]


def test_unknown_hours_do_not_limit_the_strength() -> None:
    assert dim(run(job(employment_types=("contractor_b2b",))), ENGAGEMENT).strength == Decimal(
        "1.0000"
    )


def test_no_engagement_type_is_unknown() -> None:
    assert dim(run(job()), ENGAGEMENT).status == "unknown"


# --- compensation (7.5) ----------------------------------------------------------------------------------

PAY = "compensation"


def employee(low: float, high: float, period: str = "year", currency: str = "EUR"):  # type: ignore[no-untyped-def]
    return job(
        employment_types=("employee_permanent",),
        pay=pay("annual_salary", low, high, period, currency),
    )


def contractor(form: str, low: float, high: float, period: str):  # type: ignore[no-untyped-def]
    return job(employment_types=("contractor_b2b",), pay=pay(form, low, high, period))


def test_no_stated_pay_is_unknown() -> None:
    assert dim(run(job()), PAY).status == "unknown"


def test_pay_at_or_above_the_target_scores_full() -> None:
    assert dim(run(employee(70000, 80000)), PAY).strength == Decimal(
        "1.0000"
    )  # midpoint 75,000 = target


def test_pay_between_minimum_and_target_is_interpolated() -> None:
    # midpoint 65,000: 0.25 + 0.75 * (5,000 / 15,000) = 0.5
    assert dim(run(employee(65000, 65000)), PAY).strength == Decimal("0.5000")


def test_pay_at_the_minimum_scores_a_quarter() -> None:
    result = dim(run(employee(55000, 60000)), PAY)  # midpoint 57,500 <= minimum, high = minimum
    assert (result.status, result.strength) == ("match", Decimal("0.2500"))


def test_pay_wholly_below_the_minimum_is_a_mismatch_and_fires_g10_when_asked() -> None:
    evaluation = run(employee(50000, 55000))
    assert (dim(evaluation, PAY).status, dim(evaluation, PAY).strength) == (
        "mismatch",
        Decimal("0.0000"),
    )
    assert gate_codes(evaluation) == ["G10"]
    lenient = run(employee(50000, 55000), intent(reject_below_minimum=False))
    assert gate_codes(lenient) == [] and dim(lenient, PAY).status == "mismatch"


def test_monthly_pay_uses_the_intents_payments_per_year_and_records_the_assumption() -> None:
    result = dim(run(employee(5000, 5000, "month")), PAY)  # 14 x 5,000 = 70,000
    assert result.evidence["job_range"] == [70000.0, 70000.0]
    assert result.evidence["assumptions"] == ["monthly pay x 14 payments per year"]


def test_contractor_day_rates_are_compared_with_the_day_rate_expectation() -> None:
    assert dim(run(contractor("day_rate", 500, 600, "day")), PAY).strength == Decimal(
        "1.0000"
    )  # 550 = target
    assert dim(run(contractor("day_rate", 300, 400, "day")), PAY).status == "mismatch"


def test_hourly_pay_becomes_a_day_rate_with_eight_hours() -> None:
    result = dim(run(contractor("hourly_rate", 60, 60, "hour")), PAY)  # 480 per day
    assert result.evidence["job_range"] == [480.0, 480.0]
    assert result.strength == Decimal("0.4750")  # 0.25 + 0.75 * 30 / 100
    assert result.evidence["assumptions"] == ["hourly pay x 8 hours per day"]


def test_a_different_currency_is_unknown() -> None:
    assert dim(run(employee(70000, 80000, currency="GBP")), PAY).status == "unknown"


def test_no_expectation_for_the_form_is_unknown() -> None:
    assert dim(run(employee(70000, 80000), intent(employee_pay=None)), PAY).status == "unknown"
    assert (
        dim(run(contractor("day_rate", 500, 600, "day"), intent(contractor_pay=None)), PAY).status
        == "unknown"
    )


def test_forms_that_cannot_be_compared_are_unknown() -> None:
    assert dim(run(contractor("annual_salary", 70000, 80000, "year")), PAY).status == "unknown"
    day_for_employee = job(
        employment_types=("employee_permanent",), pay=pay("day_rate", 500, 600, "day")
    )
    assert dim(run(day_for_employee), PAY).status == "unknown"


def test_the_form_follows_the_pay_when_the_engagement_type_is_unknown() -> None:
    annual = job(pay=pay("annual_salary", 70000, 80000, "year"))
    day = job(pay=pay("day_rate", 500, 600, "day"))
    assert dim(run(annual), PAY).strength == Decimal("1.0000")
    assert dim(run(day), PAY).strength == Decimal("1.0000")


# --- seniority ------------------------------------------------------------------------------------------------

SENIORITY = "seniority_experience"


def test_the_best_allowed_level_counts() -> None:
    assert dim(run(job(seniority_levels=("mid", "senior"))), SENIORITY).strength == Decimal(
        "1.0000"
    )
    assert dim(run(job(seniority_levels=("mid",))), SENIORITY).strength == Decimal("0.5000")


def test_every_allowed_level_rejected_fires_g4() -> None:
    assert gate_codes(run(job(seniority_levels=("junior",)))) == ["G4"]


def test_unknown_seniority_is_unknown() -> None:
    assert dim(run(job()), SENIORITY).status == "unknown"


# --- domain & sector ------------------------------------------------------------------------------------------

SECTOR = "domain_sector"


def test_the_primary_sector_stance_scores() -> None:
    assert dim(run(job(sector_primary="telecom")), SECTOR).strength == Decimal("1.0000")
    assert dim(run(job(sector_primary="enterprise_it")), SECTOR).strength == Decimal("0.5000")


def test_a_rejected_primary_sector_fires_g5() -> None:
    assert gate_codes(run(job(sector_primary="gambling"))) == ["G5"]


def test_an_unlisted_sector_is_a_mismatch_without_a_gate() -> None:
    evaluation = run(job(sector_primary="education"))
    assert dim(evaluation, SECTOR).status == "mismatch" and gate_codes(evaluation) == []


def test_an_unknown_sector_is_unknown() -> None:
    assert dim(run(job()), SECTOR).status == "unknown"


# --- company profile ------------------------------------------------------------------------------------------

COMPANY = "company_profile"


def test_the_employer_type_stance_scores_and_rejected_fires_g6() -> None:
    assert dim(run(job(employer_type="direct_employer")), COMPANY).strength == Decimal("1.0000")
    assert gate_codes(run(job(employer_type="consultancy_outsourcer"))) == ["G6"]
    assert dim(run(job()), COMPANY).status == "unknown"


# --- optional dimensions ---------------------------------------------------------------------------------------

BENEFITS, QUALIFICATIONS = "benefits_flexibility", "qualifications"


def test_optional_dimensions_are_excluded_by_default_but_still_evaluated() -> None:
    result = dim(run(job()), BENEFITS)
    assert (
        result.excluded is True
        and result.effective_weight == Decimal("0.00")
        and result.contribution == Decimal("0.0")
    )


def test_benefits_are_the_fraction_of_wanted_ones_mentioned() -> None:
    wanted = intent(benefits_wanted=("equity", "flexible_hours"))
    assert dim(run(job(benefits_mentioned=("equity",)), wanted), BENEFITS).strength == Decimal(
        "0.5000"
    )
    assert dim(run(job(benefits_mentioned=("pension",)), wanted), BENEFITS).status == "mismatch"
    assert dim(run(job(), wanted), BENEFITS).status == "unknown"
    assert (
        dim(run(job(benefits_mentioned=("equity",))), BENEFITS).status == "unknown"
    )  # none wanted


@pytest.mark.parametrize(
    ("required", "held", "status"),
    [
        ("bachelor", ("msc",), "match"),
        ("Bachelor", ("bachelor",), "match"),
        ("phd", ("msc",), "mismatch"),
        ("master", ("bachelor",), "mismatch"),
        ("something odd", ("msc",), "unknown"),
    ],
)
def test_qualifications_compare_education_levels(
    required: str, held: tuple[str, ...], status: str
) -> None:
    result = dim(
        run(job(education_required=required), the_profile=profile(education_levels=held)),
        QUALIFICATIONS,
    )
    assert result.status == status


def test_no_education_requirement_is_unknown() -> None:
    assert dim(run(job()), QUALIFICATIONS).status == "unknown"


def test_an_optional_dimension_with_weight_counts_when_enabled() -> None:
    weights = {**intent().weights, "qualifications": 10}
    evaluation = run(job(education_required="bachelor"), intent(weights=weights))
    assert dim(evaluation, QUALIFICATIONS).excluded is False
    assert dim(evaluation, QUALIFICATIONS).contribution > 0


def test_jobskill_is_importable_for_builders() -> None:
    assert JobSkill(1, "x", "must").importance == "must"
