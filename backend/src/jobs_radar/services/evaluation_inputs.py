"""Build the matching engine's inputs from stored data (document 13, sections 5 to 7).

These functions only translate; they decide nothing. Anything the extraction did not establish
stays ``None`` or empty so the engine treats it as unknown.
"""

from typing import Any

from jobs_radar.domain.matching.types import (
    IntentView,
    JobAttributes,
    JobLocation,
    JobPay,
    JobSkill,
    PayExpectation,
    ProfileView,
)
from jobs_radar.schemas.extraction import Evidenced, ExtractionOutput
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.profile import ProfileFacts

_QUOTED = (
    "work_mode",
    "remote_regions",
    "locations",
    "employment_types",
    "compensation",
    "seniority_levels",
    "sectors",
    "employer_type",
    "education_required",
    "benefits_mentioned",
    "languages_required",
    "visa_sponsorship",
)


def _known[T](attribute: Evidenced[T]) -> T | None:
    return attribute.value if attribute.status == "known" else None


def job_attributes(
    attributes: dict[str, Any], title: str, description: str, company_name: str
) -> JobAttributes:
    """Map a stored extraction (``job_extraction.attributes_json``) to :class:`JobAttributes`."""
    output = ExtractionOutput.model_validate(attributes["output"])
    languages = _known(output.languages_required)
    compensation = _known(output.compensation)
    sectors = _known(output.sectors)

    evidence = {
        name: attribute.evidence
        for name in _QUOTED
        if (attribute := getattr(output, name)).status == "known" and attribute.evidence
    }
    if output.role_families:
        evidence["role_families"] = output.role_families[0].evidence

    locations = tuple(
        JobLocation(
            raw=item["raw"],
            latitude=item.get("latitude") if item.get("resolved") else None,
            longitude=item.get("longitude") if item.get("resolved") else None,
        )
        for item in attributes.get("locations_resolved", [])
    )
    regions = _known(output.remote_regions)
    employment = _known(output.employment_types)
    seniority = _known(output.seniority_levels)
    benefits = _known(output.benefits_mentioned)
    return JobAttributes(
        title=title,
        description=description,
        company_name=company_name,
        role_families=tuple((r.key, r.confidence) for r in output.role_families),
        work_mode=_known(output.work_mode),
        remote_regions=tuple(regions) if regions is not None else None,
        locations=locations,
        employment_types=tuple(employment) if employment is not None else None,
        hours=_known(output.hours),
        pay=(
            JobPay(
                form=compensation.form,
                currency=compensation.currency,
                minimum=compensation.min,
                maximum=compensation.max,
                period=compensation.period,
            )
            if compensation is not None
            else None
        ),
        seniority_levels=tuple(seniority) if seniority is not None else None,
        sector_primary=sectors.primary if sectors is not None else None,
        skills=tuple(
            JobSkill(s["skill_id"], s["name"], s["importance"])
            for s in attributes.get("skills_resolved", [])
        ),
        languages_required=tuple(lang.language for lang in languages) if languages else None,
        employer_type=_known(output.employer_type),
        education_required=_known(output.education_required),
        benefits_mentioned=tuple(benefits) if benefits is not None else None,
        visa_sponsorship=_known(output.visa_sponsorship),
        evidence=evidence,
    )


def profile_view(facts: ProfileFacts) -> ProfileView:
    """Map profile facts to what matching needs."""
    return ProfileView(
        skill_levels={skill.skill_id: skill.level for skill in facts.skills},
        languages=frozenset(item.language for item in facts.languages),
        education_levels=tuple(item.level for item in facts.education),
        certifications=tuple(item.name for item in facts.certifications),
    )


def intent_view(definition: IntentDefinition) -> IntentView:
    """Map an intent revision to what matching needs."""
    stances = definition.stances
    pay = definition.compensation
    return IntentView(
        stances={
            group: {entry.key: entry.stance.value for entry in getattr(stances, group)}
            for group in (
                "role_families",
                "work_arrangements",
                "engagement_types",
                "seniority_levels",
                "sectors",
                "employer_types",
            )
        },
        part_time=stances.hours.part_time.value,
        remote_regions=tuple(definition.work_rules.remote.eligible_regions),
        base_latitude=definition.work_rules.onsite_hybrid.latitude,
        base_longitude=definition.work_rules.onsite_hybrid.longitude,
        radius_km=definition.work_rules.onsite_hybrid.radius_km,
        employee_pay=(
            PayExpectation(
                pay.employee_pay.currency,
                pay.employee_pay.annual_minimum,
                pay.employee_pay.annual_target,
                pay.employee_pay.payments_per_year,
            )
            if pay.employee_pay
            else None
        ),
        contractor_pay=(
            PayExpectation(
                pay.contractor_day_rate.currency,
                pay.contractor_day_rate.minimum,
                pay.contractor_day_rate.target,
            )
            if pay.contractor_day_rate
            else None
        ),
        reject_below_minimum=pay.reject_below_minimum,
        can_work_in=frozenset(definition.languages.can_work_in),
        reject_unspoken_required=definition.languages.reject_unspoken_required,
        excluded_companies=tuple(definition.exclusions.companies),
        excluded_words=tuple(definition.exclusions.words),
        needs_visa=definition.filters.needs_visa_or_relocation,
        benefits_wanted=tuple(definition.benefits_wanted),
        weights=definition.weights.model_dump(),
    )
