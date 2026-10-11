"""The technologies and key facts of the job briefing, read from a stored extraction (ADR-059)."""

from typing import Any

from tests.data import sample_extraction_output

from jobs_radar.domain.job_brief import key_facts, technologies


def output(**changes: Any) -> dict[str, Any]:
    return {**sample_extraction_output(), **changes}


def known(value: Any) -> dict[str, Any]:
    return {"value": value, "status": "known", "confidence": 0.9, "evidence": "x"}


UNKNOWN = {"value": None, "status": "unknown", "confidence": 0.0, "evidence": None}


def test_technologies_list_required_first_then_preferred_without_repeats() -> None:
    skills = [
        {"name": "Kafka", "importance": "nice", "evidence": "q"},
        {"name": "Java", "importance": "must", "evidence": "q"},
        {"name": "java", "importance": "nice", "evidence": "q"},
        {"name": "Oracle BRM", "importance": "must", "evidence": "q"},
    ]
    assert technologies(output(skills=skills)) == [
        {"name": "Java", "importance": "must"},
        {"name": "Oracle BRM", "importance": "must"},
        {"name": "Kafka", "importance": "nice"},
    ]


def test_no_skills_means_no_technologies() -> None:
    assert technologies(output(skills=[])) == []
    assert technologies({}) == []


def test_key_facts_are_short_labels_in_a_fixed_order() -> None:
    facts = key_facts(
        output(
            seniority_levels=known(["senior"]),
            years_required_min=known(10),
            work_mode=known("remote"),
            employment_types=known(["contractor_b2b"]),
            compensation=known(
                {
                    "form": "annual_salary",
                    "currency": "EUR",
                    "min": 60000,
                    "max": 80000,
                    "period": "year",
                    "disclosed": True,
                }
            ),
        )
    )
    assert facts == ["Senior", "10+ years", "Remote", "Contractor b2b", "EUR 60,000-80,000 / year"]


def test_one_pay_figure_is_shown_once_and_the_work_mode_reads_naturally() -> None:
    pay = {
        "form": "day_rate",
        "currency": "EUR",
        "min": 450,
        "max": 450,
        "period": "day",
        "disclosed": True,
    }
    onsite = key_facts(output(compensation=known(pay), work_mode=known("onsite")))
    hybrid = key_facts(output(compensation=known(pay), work_mode=known("hybrid")))
    assert "On site" in onsite and "Hybrid" in hybrid
    assert onsite[-1] == "EUR 450 / day"


def test_unknown_facts_are_left_out() -> None:
    facts = key_facts(
        output(
            seniority_levels=UNKNOWN,
            years_required_min=UNKNOWN,
            work_mode=UNKNOWN,
            employment_types=UNKNOWN,
            compensation=UNKNOWN,
        )
    )
    assert facts == []
