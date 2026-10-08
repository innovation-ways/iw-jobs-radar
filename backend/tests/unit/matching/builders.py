"""Builders for matching tests: a typical job, profile and intent that tests tweak."""

from dataclasses import replace
from typing import Any

from jobs_radar.domain.matching.engine import evaluate
from jobs_radar.domain.matching.types import (
    DimensionResult,
    Evaluation,
    IntentView,
    JobAttributes,
    JobLocation,
    JobPay,
    JobSkill,
    PayExpectation,
    ProfileView,
    SkillRelations,
)

DEFAULT_WEIGHTS = {
    "role_responsibilities": 25,
    "skills_technology": 15,
    "work_arrangement_location": 15,
    "engagement_terms": 10,
    "compensation": 10,
    "seniority_experience": 8,
    "domain_sector": 10,
    "company_profile": 7,
    "benefits_flexibility": 0,
    "qualifications": 0,
}
LISBON = JobLocation("Lisbon, Portugal", 38.72509, -9.1498)
SETUBAL = JobLocation("Setúbal, Portugal", 38.5244, -8.8882)
BERLIN = JobLocation("Berlin, Germany", 52.52437, 13.41053)


def intent(**changes: Any) -> IntentView:
    base = IntentView(
        stances={
            "role_families": {
                "ai_solutions_engineering": "preferred",
                "software_engineering_general": "acceptable",
                "data_analysis": "rejected",
            },
            "work_arrangements": {
                "remote": "preferred",
                "hybrid": "acceptable",
                "onsite": "acceptable",
            },
            "engagement_types": {
                "contractor_b2b": "preferred",
                "freelance": "preferred",
                "employee_permanent": "acceptable",
                "internship": "rejected",
            },
            "seniority_levels": {
                "senior": "preferred",
                "staff_principal": "preferred",
                "mid": "acceptable",
                "junior": "rejected",
            },
            "sectors": {
                "telecom": "preferred",
                "enterprise_it": "acceptable",
                "finance_banking": "acceptable",
                "gambling": "rejected",
            },
            "employer_types": {
                "direct_employer": "preferred",
                "agency": "acceptable",
                "consultancy_outsourcer": "rejected",
            },
        },
        part_time="rejected",
        remote_regions=("EU", "UK"),
        base_latitude=38.72,
        base_longitude=-9.14,
        radius_km=40,
        employee_pay=PayExpectation("EUR", 60000, 75000, 14),
        contractor_pay=PayExpectation("EUR", 450, 550),
        reject_below_minimum=True,
        can_work_in=frozenset({"pt", "en"}),
        reject_unspoken_required=True,
        weights=dict(DEFAULT_WEIGHTS),
    )
    return replace(base, **changes)


def profile(**changes: Any) -> ProfileView:
    base = ProfileView(
        skill_levels={1: "expert", 2: "advanced"},
        languages=frozenset({"pt", "en"}),
        education_levels=("msc",),
        certifications=(),
    )
    return replace(base, **changes)


def job(**changes: Any) -> JobAttributes:
    """A job with every attribute unknown except its title, so tests set only what they test."""
    base = JobAttributes(title="Senior AI Engineer", description="A good job.", company_name="Acme")
    return replace(base, **changes)


def run(
    the_job: JobAttributes | None = None,
    the_intent: IntentView | None = None,
    the_profile: ProfileView | None = None,
    relations: SkillRelations | None = None,
) -> Evaluation:
    return evaluate(
        the_job or job(), the_profile or profile(), the_intent or intent(), relations or {}
    )


def dim(evaluation: Evaluation, key: str) -> DimensionResult:
    return next(d for d in evaluation.dimensions if d.key == key)


def gate_codes(evaluation: Evaluation) -> list[str]:
    return [g.code for g in evaluation.gates]


def remote_job(**changes: Any) -> JobAttributes:
    return job(work_mode="remote", remote_regions=("EU",), **changes)


def skills(*items: tuple[int, str]) -> tuple[JobSkill, ...]:
    return tuple(JobSkill(skill_id=i, name=f"skill{i}", importance=imp) for i, imp in items)  # type: ignore[arg-type]


def pay(form: str, low: float, high: float, period: str, currency: str = "EUR") -> JobPay:
    return JobPay(form=form, currency=currency, minimum=low, maximum=high, period=period)  # type: ignore[arg-type]
