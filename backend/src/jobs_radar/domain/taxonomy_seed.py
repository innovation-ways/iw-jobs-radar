"""Taxonomy v1 seed terms (document 13, section 2.1).

FROZEN: this is what migration 0002 inserted. Never edit it to change the live taxonomy; add a new
migration that inserts or merges terms and bumps the taxonomy version instead.
"""

TAXONOMY_SEED_V1: dict[str, tuple[str, ...]] = {
    "role_family": (
        "ai_solutions_engineering",
        "ai_ml_engineering",
        "data_engineering",
        "data_analysis",
        "software_engineering_general",
        "backend_engineering",
        "frontend_engineering",
        "devops_platform",
        "solutions_architecture",
        "enterprise_architecture",
        "telecom_billing_bss_oss",
        "product_management",
        "project_programme_management",
        "consulting_integration",
        "ai_governance_risk",
        "security",
        "qa_testing",
        "sales_account_management",
        "customer_support",
        "other",
    ),
    "sector": (
        "telecom",
        "enterprise_it",
        "software_saas",
        "finance_banking",
        "insurance",
        "public_sector",
        "healthcare",
        "retail_ecommerce",
        "manufacturing_industrial",
        "energy_utilities",
        "logistics_transport",
        "media_entertainment",
        "education",
        "consulting_services",
        "gambling",
        "defence_aerospace",
        "other",
    ),
    "seniority_level": (
        "intern",
        "junior",
        "mid",
        "senior",
        "staff_principal",
        "management",
        "executive",
    ),
    "engagement_type": (
        "employee_permanent",
        "employee_fixed_term",
        "contractor_b2b",
        "freelance",
        "internship",
    ),
    "work_arrangement": ("remote", "hybrid", "onsite"),
    "employer_type": ("direct_employer", "agency_recruiter", "consultancy_outsourcer"),
    "benefit": (
        "equity",
        "bonus",
        "learning_budget",
        "flexible_hours",
        "four_day_week",
        "health_insurance",
        "extra_leave",
        "relocation_support",
        "home_office_budget",
    ),
}

# Labels that differ from a plain "capitalised words" rendering of the key.
LABEL_OVERRIDES: dict[str, str] = {
    "ai_solutions_engineering": "AI solutions engineering",
    "ai_ml_engineering": "AI / ML engineering",
    "ai_governance_risk": "AI governance and risk",
    "telecom_billing_bss_oss": "Telecom billing (BSS/OSS)",
    "project_programme_management": "Project and programme management",
    "devops_platform": "DevOps / platform",
    "qa_testing": "QA and testing",
    "enterprise_it": "Enterprise IT",
    "software_saas": "Software / SaaS",
    "finance_banking": "Finance and banking",
    "retail_ecommerce": "Retail and e-commerce",
    "manufacturing_industrial": "Manufacturing and industrial",
    "energy_utilities": "Energy and utilities",
    "logistics_transport": "Logistics and transport",
    "media_entertainment": "Media and entertainment",
    "defence_aerospace": "Defence and aerospace",
    "staff_principal": "Staff / Principal",
    "employee_permanent": "Permanent employee",
    "employee_fixed_term": "Fixed-term employee",
    "contractor_b2b": "Contractor / B2B",
    "onsite": "On-site",
    "agency_recruiter": "Agency / recruiter",
    "consultancy_outsourcer": "Consultancy / outsourcer",
    "four_day_week": "Four-day week",
}


def label_for(key: str) -> str:
    """Human-readable label for a seed term key."""
    return LABEL_OVERRIDES.get(key, key.replace("_", " ").capitalize())
