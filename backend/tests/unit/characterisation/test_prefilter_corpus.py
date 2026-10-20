"""Characterisation of the job-board pre-filter over a fixed corpus of titles (ADR-080: C3).

``categorise`` decides which technology areas a posting belongs to. The corpus mixes technology titles,
noise and titles from other occupations. The golden file records today's answer for each. Titles from
other occupations return no area today: that is a known limitation, recorded here on purpose. Phase 5
turns the areas into pack data; the Software pack must keep every other answer unchanged, and the
golden entries for other occupations are then edited consciously (with the trades pack active).
"""

import pytest
from tests.golden import check_golden
from tests.prefilter_rules import software_rules

rules = software_rules()


def categorise(texts):  # type: ignore[no-untyped-def]
    return rules.categorise(texts)


TECHNOLOGY = (
    "Senior Backend Engineer",
    "Backend Developer (Python)",
    "Frontend Engineer - React",
    "Full Stack Developer",
    "Fullstack Engineer, TypeScript",
    "Mobile Developer (iOS)",
    "Android Engineer",
    "Software Engineer, Payments",
    "Java Developer",
    "Golang Backend Engineer",
    "Rust Systems Programmer",
    "PHP Developer",
    "Ruby on Rails Engineer",
    "Kotlin Developer",
    "QA Engineer",
    "SDET - Automation",
    "Integration Engineer",
    "Solutions Engineer",
    "Solutions Architect",
    "Solution Consultant",
    "Data Engineer",
    "Senior Data Scientist",
    "Machine Learning Engineer",
    "ML Platform Engineer",
    "AI Engineer",
    "Artificial Intelligence Researcher",
    "LLM Application Developer",
    "MLOps Engineer",
    "ETL Developer",
    "BI Analyst",
    "Business Intelligence Developer",
    "Database Administrator (SQL)",
    "Analytics Engineer",
    "DevOps Engineer",
    "Site Reliability Engineer",
    "SRE",
    "Infrastructure Engineer",
    "Cloud Engineer (AWS)",
    "Kubernetes Platform Engineer",
    "Platform Engineer",
    "Systems Administrator",
    "Sysadmin Linux",
    "Terraform Specialist",
    "BSS/OSS Architect",
    "Billing Consultant",
    "Telecom Solutions Lead",
    "Telecommunications Engineer",
    "Charging and Mediation Specialist",
    "Revenue Assurance Analyst",
    "Convergent Billing Developer",
    "Security Engineer",
    "Cybersecurity Analyst",
    "InfoSec Specialist",
    "AppSec Engineer",
    "Penetration Tester",
    "Pentester",
    "Backend Developer - Cloud / Security",
    "Data & AI Engineer",
)

NOISE = (
    "AI Data Annotator",
    "Data Annotation Specialist (remote)",
    "Transcription Specialist",
    "Linguist - AI Training",
    "Audio Rater",
    "Translator (English to Portuguese)",
    "Data Labelling Analyst",
    "Talent Pool - Software",
    "Initiativbewerbung Software Developer",
    "Data Entry Clerk",
    "Online Data Analyst",
    "Sound Designer",
)

OTHER_OCCUPATIONS = (
    "Electrician",
    "Maintenance Electrician (industrial)",
    "Plumber",
    "HVAC Technician",
    "Carpenter",
    "Welder",
    "Mechanic",
    "Warehouse Operative",
    "Delivery Driver (category B licence)",
    "Forklift Operator",
    "Registered Nurse",
    "Care Assistant",
    "Pharmacy Technician",
    "Sales Assistant",
    "Cashier",
    "Customer Service Agent",
    "Waiter",
    "Chef de Partie",
    "Hotel Receptionist",
    "Accountant",
    "Payroll Administrator",
    "HR Business Partner",
    "Office Administrator",
    "Primary School Teacher",
    "Marketing Manager",
    "Graphic Designer",
    "Civil Engineer",
    "Mechanical Engineer",
    "Wind Turbine Technician",
    "Production Operator",
)

EDGE_CASES = (
    "",
    "Engineer",
    "Senior Engineer",
    "Manager",
    "Hardware Engineer",
    "Backend-Developer",
    "back_end developer",
    "AI/ML Engineer",
    "Data/Analytics Lead",
    "DEVOPS ENGINEER",
    "Java",
    "Javascript Developer",
    "Pythonista",
    "Cloudera Specialist",
    "Security Guard",
    "Data Entry and Security Clerk",
)

CORPUS = TECHNOLOGY + NOISE + OTHER_OCCUPATIONS + EDGE_CASES


def test_the_corpus_is_large_enough_to_mean_something() -> None:
    assert len(CORPUS) >= 80
    assert len(set(CORPUS)) == len(CORPUS)


def test_c3_prefilter_answers_are_unchanged() -> None:
    check_golden("prefilter_corpus", {title: sorted(categorise([title])) for title in CORPUS})


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        (["Developer", "backend", "python"], ["software"]),
        (["Engineer", "Telecom", "Billing"], ["telecom"]),
        (["Data Annotator", "Software"], []),  # noise in any part rules the posting out
        (["Plumber", "Construction"], []),
    ],
)
def test_c3_titles_tags_and_categories_are_read_together(
    texts: list[str], expected: list[str]
) -> None:
    assert sorted(categorise(texts)) == expected
