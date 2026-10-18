"""The fictional person behind the demo: a career profile and a search intent.

The persona is a senior backend and data-platform engineer based in Porto who wants remote work
inside the EU. Every value is invented; nothing resembles a real CV.
"""

from typing import Any

from jobs_radar.domain.taxonomy_additions import TAXONOMY_V2_ADDITIONS
from jobs_radar.domain.taxonomy_seed import TAXONOMY_SEED_V1

DEMO_PROFILE_TITLE = "Demo profile"

# Role families the persona does not want: the matching engine rejects them with gate G1.
_REJECTED_ROLES = (
    "sales_account_management",
    "customer_support",
    "finance_accounting",
    "legal_compliance",
    "hr_recruiting",
    "marketing_communications",
    "design_creative",
)
_PREFERRED_ROLES = ("backend_engineering", "data_engineering", "devops_platform")
_ACCEPTABLE_ROLES = (
    "software_engineering_general",
    "ai_ml_engineering",
    "solutions_architecture",
)


def demo_profile() -> dict[str, Any]:
    """Return the persona's profile as the owner would type it (a fresh dictionary each call)."""
    return {
        "headline": "Senior backend and data-platform engineer",
        "base_location": {
            "place": "Porto, Portugal",
            "country": "PT",
            "timezone": "Europe/Lisbon",
            "latitude": 41.15,
            "longitude": -8.61,
        },
        "years_experience": 11,
        "languages": [
            {"language": "pt", "level": "native"},
            {"language": "en", "level": "C1"},
            {"language": "es", "level": "B2"},
        ],
        "skills": [
            {"name": "Python", "kind": "technology", "level": "expert", "years": 10},
            {"name": "PostgreSQL", "kind": "technology", "level": "expert", "years": 9},
            {"name": "FastAPI", "kind": "technology", "level": "advanced", "years": 5},
            {"name": "Kafka", "kind": "technology", "level": "advanced", "years": 5},
            {"name": "Kubernetes", "kind": "technology", "level": "advanced", "years": 5},
            {"name": "AWS", "kind": "technology", "level": "advanced", "years": 6},
            {"name": "Terraform", "kind": "technology", "level": "intermediate", "years": 3},
            {"name": "Go", "kind": "technology", "level": "intermediate", "years": 3},
            {"name": "Apache Airflow", "kind": "technology", "level": "advanced", "years": 4},
        ],
        "experience": [
            {
                "title": "Senior Backend Engineer",
                "organisation": "Example Logistics Ltd",
                "start": "2020-03",
                "end": None,
                "summary": "Owns the event-driven order platform and its data pipelines.",
                "sectors": ["logistics_transport", "software_saas"],
            },
            {
                "title": "Backend Engineer",
                "organisation": "Sample Payments SA",
                "start": "2015-09",
                "end": "2020-02",
                "summary": "Built payment APIs and the reconciliation batch jobs.",
                "sectors": ["finance_banking"],
            },
        ],
        "education": [{"level": "msc", "field": "Computer Engineering"}],
        "certifications": [{"name": "AWS Solutions Architect Associate", "year": 2022}],
        "directions": [
            {
                "label": "Data platforms",
                "text": "Building the data platform of a product company: streaming, "
                "orchestration and reliable pipelines, rather than analytics dashboards.",
                "enabled": True,
            }
        ],
    }


def _stances(
    kind: str, preferred: tuple[str, ...] = (), rejected: tuple[str, ...] = ()
) -> list[dict[str, str]]:
    """Stance entries for every term of ``kind``; unlisted terms are acceptable."""
    keys = TAXONOMY_SEED_V1[kind]
    if kind == "role_family":
        keys = (*keys, *TAXONOMY_V2_ADDITIONS["role_family"])
    return [
        {
            "key": key,
            "stance": "preferred"
            if key in preferred
            else "rejected"
            if key in rejected
            else "acceptable",
        }
        for key in keys
    ]


def demo_intent() -> dict[str, Any]:
    """Return the persona's search intent (a fresh dictionary each call)."""
    return {
        "schema_version": 1,
        "title": "Remote backend and data roles in the EU",
        "stances": {
            "role_families": _stances("role_family", _PREFERRED_ROLES, _REJECTED_ROLES),
            "work_arrangements": _stances("work_arrangement", ("remote",), ("onsite",)),
            "engagement_types": _stances(
                "engagement_type", ("employee_permanent",), ("internship",)
            ),
            "hours": {"part_time": "rejected"},
            "seniority_levels": _stances(
                "seniority_level",
                ("senior", "staff_principal"),
                ("intern", "junior"),
            ),
            "sectors": _stances("sector", ("software_saas", "logistics_transport"), ("gambling",)),
            "employer_types": _stances(
                "employer_type", ("direct_employer",), ("agency_recruiter",)
            ),
        },
        "work_rules": {
            "remote": {
                "eligible_regions": ["EU"],
                "timezone": "Europe/Lisbon",
                "timezone_tolerance_hours": 2,
            },
            "onsite_hybrid": {
                "base_place": "Porto, Portugal",
                "latitude": 41.15,
                "longitude": -8.61,
                "radius_km": 30,
            },
        },
        "compensation": {
            "employee_pay": {
                "currency": "EUR",
                "payments_per_year": 14,
                "annual_minimum": 55000,
                "annual_target": 72000,
            },
            "contractor_day_rate": {"currency": "EUR", "minimum": 400, "target": 520},
            "reject_below_minimum": False,
        },
        "languages": {"can_work_in": ["pt", "en", "es"], "reject_unspoken_required": True},
        "keywords": ["Python", "Kafka", "data platform", "event-driven"],
        "exclusions": {"companies": [], "words": ["unpaid"]},
        "filters": {"max_posting_age_days": None, "needs_visa_or_relocation": False},
        "benefits_wanted": ["learning_budget", "flexible_hours"],
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
            "career_direction": 0,
        },
        "alert_threshold": 65,
    }
