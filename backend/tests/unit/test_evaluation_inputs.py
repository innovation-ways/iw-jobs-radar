"""Mapping stored extractions, profiles and intents to the engine's inputs."""

from decimal import Decimal

from tests.data import (
    SAMPLE_JOB_DESCRIPTION,
    SAMPLE_JOB_TITLE,
    sample_extraction_output,
    sample_intent,
    sample_profile_facts,
)

from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.profile import ProfileFacts
from jobs_radar.services.evaluation_inputs import intent_view, job_attributes, profile_view


def stored(**changes: object) -> dict[str, object]:
    return {
        "output": sample_extraction_output(),
        "unverified": [],
        "dropped_keys": [],
        "contradictions": [],
        "skills_resolved": [
            {"skill_id": 17, "name": "Python", "importance": "must"},
            {"skill_id": 18, "name": "API design", "importance": "nice"},
        ],
        "locations_resolved": [
            {
                "raw": "Lisbon, Portugal",
                "resolved": True,
                "city": "Lisbon",
                "country": "PT",
                "latitude": 38.7,
                "longitude": -9.1,
                "timezone": "Europe/Lisbon",
            },
            {"raw": "Remote - EU", "resolved": False},
        ],
        **changes,
    }


def test_a_stored_extraction_becomes_job_attributes() -> None:
    job = job_attributes(stored(), SAMPLE_JOB_TITLE, SAMPLE_JOB_DESCRIPTION, "Acme")
    assert (job.title, job.description, job.company_name) == (
        SAMPLE_JOB_TITLE,
        SAMPLE_JOB_DESCRIPTION,
        "Acme",
    )
    assert job.role_families == (("ai_solutions_engineering", 0.93),)
    assert (job.work_mode, job.remote_regions) == ("remote", ("EU",))
    assert job.employment_types == ("contractor_b2b",) and job.hours is None
    assert job.seniority_levels == ("senior",) and job.sector_primary == "enterprise_it"
    assert job.employer_type == "direct_employer" and job.languages_required == ("en",)
    assert job.benefits_mentioned == ("flexible_hours",)
    assert job.pay is None and job.visa_sponsorship is None and job.education_required is None
    assert [(s.skill_id, s.importance) for s in job.skills] == [(17, "must"), (18, "nice")]


def test_resolved_locations_carry_coordinates_and_unresolved_ones_do_not() -> None:
    job = job_attributes(stored(), "t", "d", "Acme")
    assert [(loc.raw, loc.latitude, loc.longitude) for loc in job.locations] == [
        ("Lisbon, Portugal", 38.7, -9.1),
        ("Remote - EU", None, None),
    ]


def test_evidence_quotes_are_carried_for_the_results() -> None:
    job = job_attributes(stored(), SAMPLE_JOB_TITLE, SAMPLE_JOB_DESCRIPTION, "Acme")
    assert job.evidence["work_mode"] == "Fully remote within EU time zones."
    assert job.evidence["role_families"] == "Design and evaluate LLM-powered features"
    assert "compensation" not in job.evidence  # unknown attributes have no quote


def test_stated_pay_is_mapped_as_stated() -> None:
    output = sample_extraction_output()
    output["compensation"] = {
        "value": {
            "form": "day_rate",
            "currency": "EUR",
            "min": 500,
            "max": 600,
            "period": "day",
            "disclosed": True,
        },
        "status": "known",
        "confidence": 0.9,
        "evidence": "500 to 600 EUR per day",
    }
    job = job_attributes(stored(output=output), "t", "d", "Acme")
    assert job.pay is not None and (
        job.pay.form,
        job.pay.minimum,
        job.pay.maximum,
        job.pay.period,
    ) == ("day_rate", 500, 600, "day")


def test_a_profile_becomes_skill_levels_languages_and_education() -> None:
    view = profile_view(ProfileFacts.model_validate(sample_profile_facts()))
    assert view.skill_levels == {17: "expert", 18: "advanced"}
    assert view.languages == frozenset({"pt", "en"})
    assert view.education_levels == ("msc",) and view.certifications == ("Example Certification",)


def test_an_intent_becomes_stances_rules_pay_and_weights() -> None:
    view = intent_view(IntentDefinition.model_validate(sample_intent()))
    assert view.stances["role_families"]["ai_solutions_engineering"] == "preferred"
    assert view.stances["work_arrangements"]["remote"] == "preferred"
    assert view.part_time == "rejected"
    assert view.remote_regions == ("EU", "UK")
    assert (view.base_latitude, view.base_longitude, view.radius_km) == (38.72, -9.14, 40)
    assert view.employee_pay is not None
    assert (
        view.employee_pay.currency,
        view.employee_pay.minimum,
        view.employee_pay.target,
        view.employee_pay.payments_per_year,
    ) == ("EUR", 60000, 75000, 14)
    assert view.contractor_pay is not None and (
        view.contractor_pay.minimum,
        view.contractor_pay.target,
    ) == (450, 550)
    assert view.can_work_in == frozenset({"pt", "en"}) and view.reject_unspoken_required is True
    assert view.weights["compensation"] == 10 and view.weights["qualifications"] == 0
    assert Decimal(view.weights["role_responsibilities"]) == 25
