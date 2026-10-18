"""Turns a :class:`~jobs_radar.demo.jobs.DemoJob` into posting text and into the extraction answer.

Both come from the same record, and every quote of the extraction is copied from a sentence written
here, so the real evidence check (``verify_evidence``) accepts all of them. This is what lets the
demo run the production extraction and scoring code without a model.
"""

from typing import Any

from jobs_radar.demo.jobs import DemoJob

_SENIORITY_WORDS = {
    "intern": "an internship",
    "junior": "an entry-level engineer",
    "mid": "a mid-level engineer",
    "senior": "a senior engineer",
    "staff_principal": "a staff-level engineer",
    "management": "a people manager",
    "executive": "an executive",
}
_ENGAGEMENT_PHRASES = {
    "employee_permanent": "permanent employment contract",
    "employee_fixed_term": "fixed-term employment contract",
    "contractor_b2b": "B2B contract",
    "contractor_agency": "contract through our agency",
    "freelance": "freelance engagement",
    "internship": "paid internship",
}
_SECTOR_PHRASES = {
    "software_saas": "We build software as a service for developers.",
    "logistics_transport": "We build software for the logistics industry.",
    "enterprise_it": "We build infrastructure for large enterprise customers.",
    "finance_banking": "We are a bank serving retail customers.",
    "healthcare": "We build software for hospitals and clinics.",
    "telecom": "We operate a telecom network in the Iberian market.",
    "retail_ecommerce": "We help retailers forecast demand.",
    "gambling": "We operate online betting and gaming products.",
    "energy_utilities": "We build software for the renewable energy industry.",
    "consulting_services": "We provide consulting and staffing services.",
    "insurance": "We build core platforms for insurers.",
}
_BENEFIT_PHRASES = {
    "equity": "stock options",
    "bonus": "annual bonus",
    "learning_budget": "annual learning budget",
    "flexible_hours": "flexible working hours",
    "four_day_week": "four-day working week",
    "health_insurance": "private health insurance",
    "extra_leave": "extra holiday days",
    "relocation_support": "relocation support",
    "home_office_budget": "home-office budget",
}


def _known(value: Any, evidence: str, confidence: float = 0.9) -> dict[str, Any]:
    """Return a known attribute with its quote."""
    return {"value": value, "status": "known", "confidence": confidence, "evidence": evidence}


_UNKNOWN: dict[str, Any] = {"value": None, "status": "unknown", "confidence": 0.0, "evidence": None}


def _work_sentence(job: DemoJob) -> str:
    """Return the sentence that states the work arrangement."""
    if job.mode == "remote":
        return "This is a fully remote role."
    if job.mode == "hybrid":
        city = job.places[0].split(",")[0]
        return f"Hybrid: {job.office_days} days a week in our {city} office."
    return f"This role is based on site in {job.places[0]}."


def _pay_sentence(job: DemoJob) -> str | None:
    """Return the sentence that states the pay, or ``None`` when the posting does not."""
    if job.pay is None:
        return None
    form, low, high = job.pay
    if form == "day_rate":
        return f"Day rate: EUR {low} - {high} per day."
    return f"Salary range: EUR {low:,} - {high:,} per year."


def render_description(job: DemoJob) -> str:
    """Return the posting text: a pitch, the facts a model would extract and a requirements list."""
    lines = [f"About the role\n{job.pitch}", ""]
    lines.append(_SECTOR_PHRASES.get(job.sector, "We build software."))
    lines.append(_work_sentence(job))
    lines.append(f"Location: {'; '.join(job.places)}")
    if job.mode == "remote" and job.regions:
        lines.append(f"The role is open to candidates in {', '.join(job.regions)}.")
    lines.append(f"Engagement: {_ENGAGEMENT_PHRASES[job.employment[0]]}.")
    lines.append(
        "Part-time position (20 hours a week)."
        if job.hours == "part_time"
        else "Full-time position."
    )
    lines.append(f"We are looking for {_SENIORITY_WORDS[job.seniority[0]]}.")
    if job.years:
        lines.append(f"{job.years}+ years of professional experience.")
    if job.employer == "agency_recruiter":
        lines.append("Our client is hiring through us, a recruitment agency.")
    else:
        lines.append("We are the team that builds and runs this product ourselves.")
    pay = _pay_sentence(job)
    if pay:
        lines.append(pay)
    if job.benefits:
        lines.append("What we offer: " + ", ".join(_BENEFIT_PHRASES[b] for b in job.benefits) + ".")
    lines.append("Working language: English.")
    lines.append("")
    lines.append("Requirements")
    lines += [f"- Strong experience with {skill}" for skill in job.must]
    if job.nice:
        lines.append("Nice to have")
        lines += [f"- {skill}" for skill in job.nice]
    return "\n".join(lines)


def _compensation(job: DemoJob) -> dict[str, Any]:
    """Return the compensation attribute: known with its sentence, or unknown."""
    if job.pay is None:
        return dict(_UNKNOWN)
    form, low, high = job.pay
    value = {
        "form": form,
        "currency": "EUR",
        "min": float(low),
        "max": float(high),
        "period": "day" if form == "day_rate" else "year",
        "disclosed": True,
    }
    sentence = _pay_sentence(job)
    assert sentence is not None  # noqa: S101  # pay is set, so the sentence exists
    return _known(value, sentence, 0.95)


def render_extraction(job: DemoJob, description: str) -> dict[str, Any]:
    """Return the extraction the "model" gives for ``job``; every quote occurs in its text."""
    del description  # the quotes are rebuilt from the same sentences; the test verifies them
    location_line = f"Location: {'; '.join(job.places)}"
    remote = job.mode == "remote"
    return {
        "schema_version": 1,
        "title": _known(job.title, job.title, 1.0),
        "employment_types": _known(
            list(job.employment), _ENGAGEMENT_PHRASES[job.employment[0]], 0.9
        ),
        "hours": _known(
            job.hours,
            "Part-time position" if job.hours == "part_time" else "Full-time position",
            0.95,
        ),
        "work_mode": _known(job.mode, _work_sentence(job), 0.95),
        "remote_regions": _known(
            list(job.regions), f"open to candidates in {', '.join(job.regions)}", 0.85
        )
        if remote and job.regions
        else dict(_UNKNOWN),
        "locations": _known(list(job.places), location_line, 0.9),
        "compensation": _compensation(job),
        "seniority_levels": _known(
            list(job.seniority), _SENIORITY_WORDS[job.seniority[0]].split(" ", 1)[1], 0.85
        ),
        "years_required_min": _known(
            job.years, f"{job.years}+ years of professional experience", 0.9
        )
        if job.years
        else dict(_UNKNOWN),
        "role_families": [{"key": job.role, "confidence": 0.92, "evidence": job.pitch}],
        "sectors": _known(
            {"primary": job.sector, "secondary": list(job.secondary_sectors)},
            _SECTOR_PHRASES.get(job.sector, "We build software.").rstrip("."),
            0.8,
        ),
        "skills": [
            {"name": skill, "importance": "must", "evidence": f"Strong experience with {skill}"}
            for skill in job.must
        ]
        + [{"name": skill, "importance": "nice", "evidence": skill} for skill in job.nice],
        "languages_required": _known([{"language": "en", "level": None}], "English", 0.8),
        "employer_type": _known(
            job.employer,
            "recruitment agency"
            if job.employer == "agency_recruiter"
            else "builds and runs this product ourselves",
            0.8,
        ),
        "education_required": dict(_UNKNOWN),
        "benefits_mentioned": _known(list(job.benefits), _BENEFIT_PHRASES[job.benefits[0]], 0.8)
        if job.benefits
        else dict(_UNKNOWN),
        "visa_sponsorship": dict(_UNKNOWN),
    }
