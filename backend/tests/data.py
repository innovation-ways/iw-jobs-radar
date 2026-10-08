"""Synthetic sample data for tests (no real CVs, jobs or personal data; ADR-015).

The intent reproduces the owner-style search described in document 13, section 4, with a made-up
profile around it. Functions return fresh dictionaries so tests can modify them freely.
"""

from copy import deepcopy
from typing import Any

from jobs_radar.domain.taxonomy_seed import TAXONOMY_SEED_V1


def sample_profile_facts() -> dict[str, Any]:
    """A synthetic profile (document 13, section 3)."""
    return {
        "schema_version": 1,
        "headline": "AI solutions and integration engineer",
        "base_location": {
            "place": "Lisbon, Portugal",
            "country": "PT",
            "timezone": "Europe/Lisbon",
            "latitude": 38.72,
            "longitude": -9.14,
        },
        "years_experience": 12,
        "languages": [{"language": "pt", "level": "native"}, {"language": "en", "level": "C1"}],
        "skills": [
            {
                "skill_id": 17,
                "level": "expert",
                "years": 10,
                "provenance": {
                    "origin": "document",
                    "evidence_id": 41,
                    "accepted_at": "2026-10-08T10:00:00Z",
                },
            },
            {"skill_id": 18, "level": "advanced", "years": 4, "provenance": {"origin": "manual"}},
        ],
        "experience": [
            {
                "title": "Solutions Architect",
                "organisation": "Example Corp",
                "start": "2019-01",
                "end": "2024-06",
                "summary": "Led integration of machine-learning features into telecom platforms.",
                "sectors": ["telecom", "enterprise_it"],
                "provenance": {"origin": "manual"},
            }
        ],
        "education": [
            {"level": "msc", "field": "Computer Science", "provenance": {"origin": "manual"}}
        ],
        "certifications": [
            {"name": "Example Certification", "year": 2022, "provenance": {"origin": "manual"}}
        ],
    }


def _stances(kind: str, spec: dict[str, str]) -> list[dict[str, str]]:
    """Stance entries for every seed term of ``kind``; ``spec`` overrides the default ``acceptable``."""
    return [{"key": key, "stance": spec.get(key, "acceptable")} for key in TAXONOMY_SEED_V1[kind]]


def sample_intent() -> dict[str, Any]:
    """The worked-example intent of document 13, section 4, listing every term of the closed groups."""
    return {
        "schema_version": 1,
        "title": "AI & telecom billing — remote first",
        "stances": {
            "role_families": [
                {"key": "ai_solutions_engineering", "stance": "preferred"},
                {"key": "telecom_billing_bss_oss", "stance": "preferred"},
                {"key": "software_engineering_general", "stance": "acceptable"},
                {"key": "data_analysis", "stance": "rejected"},
                {"key": "sales_account_management", "stance": "rejected"},
            ],
            "work_arrangements": _stances("work_arrangement", {"remote": "preferred"}),
            "engagement_types": _stances(
                "engagement_type",
                {"contractor_b2b": "preferred", "freelance": "preferred", "internship": "rejected"},
            ),
            "hours": {"part_time": "rejected"},
            "seniority_levels": _stances(
                "seniority_level",
                {
                    "intern": "rejected",
                    "junior": "rejected",
                    "senior": "preferred",
                    "staff_principal": "preferred",
                },
            ),
            "sectors": [
                {"key": "telecom", "stance": "preferred"},
                {"key": "enterprise_it", "stance": "preferred"},
                {"key": "finance_banking", "stance": "acceptable"},
                {"key": "gambling", "stance": "rejected"},
            ],
            "employer_types": _stances("employer_type", {"direct_employer": "preferred"}),
        },
        "work_rules": {
            "remote": {
                "eligible_regions": ["EU", "UK"],
                "timezone": "Europe/Lisbon",
                "timezone_tolerance_hours": 2,
            },
            "onsite_hybrid": {
                "base_place": "Lisbon, Portugal",
                "latitude": 38.72,
                "longitude": -9.14,
                "radius_km": 40,
            },
        },
        "compensation": {
            "employee_pay": {
                "currency": "EUR",
                "payments_per_year": 14,
                "annual_minimum": 60000,
                "annual_target": 75000,
            },
            "contractor_day_rate": {"currency": "EUR", "minimum": 450, "target": 550},
            "reject_below_minimum": True,
        },
        "languages": {"can_work_in": ["pt", "en"], "reject_unspoken_required": True},
        "keywords": ["LLM", "RAG", "billing", "charging", "mediation"],
        "exclusions": {"companies": ["Harbor Systems"], "words": ["unpaid", "internship"]},
        "filters": {"max_posting_age_days": None, "needs_visa_or_relocation": False},
        "benefits_wanted": [],
        "weights": {
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
        },
        "alert_threshold": 65,
    }


def sample_normalised_job() -> dict[str, Any]:
    """A synthetic normalised job (document 13, section 5)."""
    return deepcopy(
        {
            "schema_version": 1,
            "title": "Senior AI Solutions Engineer",
            "description_text": "Design and evaluate LLM-powered features. Fully remote within EU time zones.",
            "employment": {
                "types": [{"value": "contractor_b2b", "status": "known"}],
                "hours": {"value": "full_time", "status": "known"},
            },
            "work_arrangement": {
                "mode": {"value": "remote", "status": "known"},
                "remote_eligibility": {
                    "status": "known",
                    "anywhere": False,
                    "regions": ["EU"],
                    "countries": [],
                    "timezone_offset_range_hours": [0, 2],
                },
                "locations": [
                    {
                        "raw": "Remote - EU",
                        "country": "",
                        "region": "EU",
                        "city": "",
                        "latitude": None,
                        "longitude": None,
                    }
                ],
            },
            "compensation": {"status": "unknown"},
            "seniority": {"levels": ["senior"], "years_required_min": 8, "status": "known"},
            "role_families": [{"key": "ai_solutions_engineering", "confidence": 0.93}],
            "sectors": {
                "primary": "enterprise_it",
                "secondary": ["finance_banking"],
                "status": "known",
            },
            "skills": {
                "required": [{"skill_id": 17, "importance": "must"}],
                "preferred": [{"skill_id": 52, "importance": "nice"}],
            },
            "languages_required": [{"language": "en", "level": "C1"}],
            "employer": {"company_id": 9, "type": {"value": "direct_employer", "status": "known"}},
            "education_required": {"level": "bachelor", "status": "known"},
            "benefits_mentioned": ["flexible_hours"],
            "visa_sponsorship": {"status": "unknown"},
            "posted_at": "2026-10-06T08:00:00Z",
            "valid_through": None,
            "source": {
                "source_type": "greenhouse",
                "external_job_id": "4461450008",
                "url": "https://jobs.example.test/4461450008",
                "apply_url": "https://jobs.example.test/4461450008/apply",
                "language": "en",
            },
        }
    )


def sample_profile_input() -> dict[str, Any]:
    """Profile as the owner edits it: skills by name, no provenance (the service adds it)."""
    facts = sample_profile_facts()
    return {
        "headline": facts["headline"],
        "base_location": facts["base_location"],
        "years_experience": facts["years_experience"],
        "languages": facts["languages"],
        "skills": [
            {"name": "Python", "kind": "technology", "level": "expert", "years": 10},
            {"name": "Kubernetes", "kind": "technology", "level": "advanced", "years": 4},
        ],
        "experience": [
            {k: v for k, v in item.items() if k != "provenance"} for item in facts["experience"]
        ],
        "education": [
            {k: v for k, v in item.items() if k != "provenance"} for item in facts["education"]
        ],
        "certifications": [
            {k: v for k, v in item.items() if k != "provenance"} for item in facts["certifications"]
        ],
    }


SAMPLE_JOB_TITLE = "Senior AI Solutions Engineer"
SAMPLE_JOB_DESCRIPTION = (
    "About the role\n"
    "Design and evaluate LLM-powered features for enterprise customers. This is a 12-month contract.\n"
    "Fully remote within EU time zones. Our customers are large enterprises in finance and telecom.\n"
    "Requirements\n"
    "- Experience with Python and API design.\n"
    "- Fluent English.\n"
    "We offer flexible hours. Join our team in Lisbon or work remotely."
)


def sample_extraction_output() -> dict[str, Any]:
    """A valid model answer whose quotes all occur in ``SAMPLE_JOB_DESCRIPTION``."""
    unknown = {"value": None, "status": "unknown", "confidence": 0.0, "evidence": None}

    def known(value: Any, quote: str, confidence: float = 0.9) -> dict[str, Any]:
        return {"value": value, "status": "known", "confidence": confidence, "evidence": quote}

    return {
        "schema_version": 1,
        "title": known(SAMPLE_JOB_TITLE, SAMPLE_JOB_TITLE, 1.0),
        "employment_types": known(["contractor_b2b"], "12-month contract"),
        "hours": unknown,
        "work_mode": known("remote", "Fully remote within EU time zones.", 0.95),
        "remote_regions": known(["EU"], "within EU time zones"),
        "locations": known(["Remote - EU"], "Fully remote within EU time zones"),
        "compensation": unknown,
        "seniority_levels": known(["senior"], SAMPLE_JOB_TITLE),
        "years_required_min": unknown,
        "role_families": [
            {
                "key": "ai_solutions_engineering",
                "confidence": 0.93,
                "evidence": "Design and evaluate LLM-powered features",
            }
        ],
        "sectors": known({"primary": "enterprise_it", "secondary": []}, "large enterprises", 0.7),
        "skills": [
            {"name": "Python", "importance": "must", "evidence": "Experience with Python"},
            {"name": "API design", "importance": "must", "evidence": "API design"},
        ],
        "languages_required": known([{"language": "en", "level": None}], "Fluent English", 0.8),
        "employer_type": known("direct_employer", "Join our team", 0.8),
        "education_required": unknown,
        "benefits_mentioned": known(["flexible_hours"], "flexible hours", 0.8),
        "visa_sponsorship": unknown,
    }
