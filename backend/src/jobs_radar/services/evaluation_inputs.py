"""Build the matching engine's inputs from stored data (document 13, sections 5 to 7).

These functions only translate; they decide nothing. Anything the extraction did not establish
stays ``None`` or empty so the engine treats it as unknown.
"""

from collections.abc import Collection, Mapping, Sequence
from typing import Any, cast

from jobs_radar.adapters.sources.countries import country_code
from jobs_radar.domain.matching.types import (
    IntentView,
    JobAttributes,
    JobLocation,
    JobPay,
    JobSkill,
    PayExpectation,
    ProfileView,
    Stance,
)
from jobs_radar.domain.regions import expand_regions
from jobs_radar.domain.taxonomy_terms import resolve_key, resolve_stances
from jobs_radar.schemas.extraction import Evidenced, ExtractionOutput
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.profile import ProfileFacts
from jobs_radar.services.remote_places import source_remote_countries

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


def _region_codes(regions: list[str]) -> tuple[str, ...]:
    """Turn country names ("Austria") into ISO codes; groups (EU), codes and others are kept.

    The model often writes a country by its name, which the matching engine cannot recognise, so
    a job open only to Austria would count as "regions not recognised" instead of a mismatch
    (ADR-052).
    """
    result: list[str] = []
    for region in regions:
        code = country_code(region) if len(region.strip()) > 2 else None
        result.append(code or region)
    return tuple(result)


def _narrowed_regions(regions: tuple[str, ...], allowed: frozenset[str]) -> tuple[str, ...]:
    """Limit the model's regions to the countries the source allows (ADR-056).

    Regions the model wrote that are inside the limit are kept as written; otherwise the shared
    countries are used, and when nothing is shared the source's own countries replace them, so the
    engine sees a recognised region that does not include the owner's (gate G2).
    """
    countries, recognised = expand_regions(regions)
    if not recognised:
        return regions  # not understood: stays a risk, as before
    if countries is not None and countries <= allowed:
        return regions
    shared = allowed if countries is None else countries & allowed
    return tuple(sorted(shared or allowed))


def _known[T](attribute: Evidenced[T]) -> T | None:
    return attribute.value if attribute.status == "known" else None


def job_attributes(
    attributes: dict[str, Any],
    title: str,
    description: str,
    company_name: str,
    source_places: Sequence[str] = (),
    replacements: Mapping[str, Mapping[str, str]] | None = None,
) -> JobAttributes:
    """Map a stored extraction (``job_extraction.attributes_json``) to :class:`JobAttributes`.

    ``source_places`` are the board's own locations; when they are all remote places bound to
    countries they limit the regions the model reported (ADR-056).
    """
    output = ExtractionOutput.model_validate(attributes["output"])
    replacements = replacements or {}
    family_keys = replacements.get("role_family", {})
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
    region_codes = _region_codes(regions) if regions is not None else None
    text_regions = region_codes  # kept for the evidence before the source limits it (ADR-069)
    allowed = source_remote_countries(source_places)
    if region_codes is None and allowed is not None and _known(output.work_mode) == "remote":
        # The model named no regions but the source's own places do (ADR-058): without this,
        # `Remote - USA` earned location points "as a risk" like any unstated region.
        region_codes = tuple(sorted(allowed))
        evidence["remote_regions"] = f"from the source location: {', '.join(source_places)}"
    elif region_codes is not None and allowed is not None:
        limited = _narrowed_regions(region_codes, allowed)
        if limited != region_codes:
            region_codes = limited
            quote = evidence.get("remote_regions")
            note = f"limited by the source location: {', '.join(source_places)}"
            evidence["remote_regions"] = f"{quote} ({note})" if quote else note
    employment = _known(output.employment_types)
    seniority = _known(output.seniority_levels)
    benefits = _known(output.benefits_mentioned)
    return JobAttributes(
        title=title,
        description=description,
        company_name=company_name,
        role_families=tuple(
            (resolve_key(family_keys, r.key), r.confidence) for r in output.role_families
        ),
        work_mode=_known(output.work_mode),
        remote_regions=region_codes,
        text_remote_regions=text_regions,
        source_places=tuple(source_places),
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
        sector_primary=(
            resolve_key(replacements.get("sector", {}), sectors.primary)
            if sectors is not None
            else None
        ),
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


# Closed groups of an intent and the taxonomy kind each one lists.
_CLOSED_GROUPS = {
    "work_arrangements": "work_arrangement",
    "engagement_types": "engagement_type",
    "seniority_levels": "seniority_level",
    "employer_types": "employer_type",
}
_OPEN_GROUPS_VIEW = {"role_families": "role_family", "sectors": "sector"}


def intent_view(
    definition: IntentDefinition,
    optional_terms: Mapping[str, Collection[str]],
    replacements: Mapping[str, Mapping[str, str]] | None = None,
) -> IntentView:
    """Map an intent revision to what matching needs.

    ``optional_terms`` are the terms added to the taxonomy after the intent may have been saved
    (``TaxonomyRepository.optional_keys_by_kind``). ``replacements`` map merged terms to the term
    that replaced them, by kind (``TaxonomyRepository.replacements``): a stance on a merged term is
    a stance on its replacement, and the replacement's own stance wins (ADR-080).
    """
    replacements = replacements or {}
    stances = definition.stances
    pay = definition.compensation
    later = optional_terms
    group_stances: dict[str, dict[str, Stance]] = {}
    for group, kind in _CLOSED_GROUPS.items():
        listed: dict[str, Stance] = {
            entry.key: cast(Stance, entry.stance.value) for entry in getattr(stances, group)
        }
        # A term added after the intent was saved is acceptable until the owner chooses (ADR-073).
        group_stances[group] = {
            **dict.fromkeys(later.get(kind, ()), "acceptable"),
            **listed,
        }
    for group, kind in _OPEN_GROUPS_VIEW.items():
        listed_open = {entry.key: entry.stance.value for entry in getattr(stances, group)}
        group_stances[group] = cast(
            dict[str, Stance], resolve_stances(listed_open, replacements.get(kind, {}))
        )
    return IntentView(
        stances=group_stances,
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
