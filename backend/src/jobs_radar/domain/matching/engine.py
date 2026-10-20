"""The ``matching-v1`` engine (document 13, section 7): a pure, deterministic function.

``evaluate(job, profile, intent, relations)`` returns the score, the band, the hard gates that
fired and one result per dimension. It imports no HTTP, database, network or model code, and it
never guesses: missing information is ``unknown`` and contributes nothing, while the dimension's
weight still counts (ADR-005, ADR-024). Exact arithmetic (fractions) is used, contributions are
rounded to one decimal half up, and the final score is the rounded sum, so results are reproducible.
"""

import re
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Any

from jobs_radar.domain.geo import haversine_km, normalise_place
from jobs_radar.domain.matching.types import (
    DIMENSION_KEYS,
    DimensionResult,
    Evaluation,
    Gate,
    IntentView,
    JobAttributes,
    PayExpectation,
    ProfileView,
    Quality,
    SkillRelations,
    Status,
)
from jobs_radar.domain.regions import regions_intersect

# matching-v1.1 (ADR-052): same rules as matching-v1; the input mapping now reads country names.
# matching-v1.2 (ADR-056): same rules; the input mapping limits the model's remote regions to what
# the source's own remote places allow.
# matching-v1.5 (ADR-058): far offices without a remote statement fire gate G2 and region groups.
# matching-v1.5 (ADR-057): the career-direction dimension (the best judged direction counts).
# matching-v1.6 (ADR-066): gate G1 also fires when the primary role family is rejected.
# matching-v1.7 (ADR-068): a bare country or region next to a remote marker limits remote work.
# matching-v1.8 (ADR-069): the location evidence names the source's places and the text's regions.
POLICY_VERSION = "matching-v1.8"

ZERO, HALF, ONE = Fraction(0), Fraction(1, 2), Fraction(1)
_STANCE = {"preferred": ONE, "acceptable": HALF, "rejected": ZERO}
_CONFIDENCE_FLOOR = 0.6
_UNVERIFIED_REMOTE_FACTOR = Fraction(4, 5)  # eligibility not stated: a risk, not a mismatch
_MUST, _NICE = 2, 1
# Strength of each judged career-direction level (ADR-057); "unknown" is handled separately.
_DIRECTION_STRENGTH = {
    "strong": ONE,
    "partial": HALF,
    "weak": Fraction(1, 5),
    "none": ZERO,
}
_HOURS_PER_DAY = 8
_EDUCATION_RANK = {
    "secondary": 1,
    "highschool": 1,
    "bachelor": 2,
    "bsc": 2,
    "ba": 2,
    "licenciatura": 2,
    "master": 3,
    "msc": 3,
    "ma": 3,
    "mba": 3,
    "mestrado": 3,
    "phd": 4,
    "doctorate": 4,
    "doctoral": 4,
}


class _Raw:
    """The outcome of one dimension before weights are applied."""

    def __init__(
        self,
        status: Status,
        strength: Fraction | None,
        evidence: Mapping[str, Any],
        explanation: str,
    ) -> None:
        self.status: Status = status
        self.strength = strength
        self.evidence = evidence
        self.explanation = explanation


def _unknown(why: str, **evidence: Any) -> _Raw:
    return _Raw("unknown", None, {"reason": why, **evidence}, why)


def _scored(strength: Fraction, evidence: Mapping[str, Any], explanation: str) -> _Raw:
    return _Raw("match" if strength > 0 else "mismatch", strength, evidence, explanation)


def _stance(intent: IntentView, group: str, key: str) -> str | None:
    """Return the owner's stance on ``key``, or ``None`` when it is not listed (unlisted)."""
    return intent.stances.get(group, {}).get(key)


def _quote(job: JobAttributes, attribute: str) -> str | None:
    return job.evidence.get(attribute)


def _best_stance(
    intent: IntentView, group: str, keys: tuple[str, ...]
) -> tuple[Fraction, bool, dict[str, str | None]]:
    """Return ``(best strength, all rejected, stance per key)`` for several candidate keys."""
    stances = {key: _stance(intent, group, key) for key in keys}
    open_strengths = [_STANCE[s] if s else ZERO for s in stances.values() if s != "rejected"]
    all_rejected = bool(stances) and all(s == "rejected" for s in stances.values())
    return (max(open_strengths) if open_strengths else ZERO), all_rejected, stances


# --- dimensions -------------------------------------------------------------------------------


def _role(job: JobAttributes, intent: IntentView, gates: list[Gate]) -> _Raw:
    families = tuple(
        key for key, confidence in job.role_families if confidence >= _CONFIDENCE_FLOOR
    )
    if not families:
        return _unknown("No role family was identified with enough confidence.")
    strength, all_rejected, stances = _best_stance(intent, "role_families", families)
    evidence = {"job_quote": _quote(job, "role_families"), "compared": stances}
    if all_rejected:
        gates.append(Gate("G1", "Every identified role family is one you rejected.", evidence))
        return _Raw("mismatch", ZERO, evidence, "All identified role families are rejected.")
    # The model lists the best-fitting family first (ADR-066): a rejected primary family is a
    # rejected job, whatever acceptable family is listed after it (a "Sales Engineer" is sales).
    if stances[families[0]] == "rejected":
        gates.append(Gate("G1", "The main role family of the job is one you rejected.", evidence))
        return _Raw("mismatch", ZERO, evidence, "The primary role family is rejected.")
    return _scored(strength, evidence, "Best stance among the identified role families.")


def _skills(job: JobAttributes, profile: ProfileView, relations: SkillRelations) -> _Raw:
    if not job.skills:
        return _unknown("The posting lists no skills.")
    earned = Fraction(0)
    total = Fraction(0)
    detail: list[dict[str, Any]] = []
    for skill in job.skills:
        weight = _MUST if skill.importance == "must" else _NICE
        if skill.skill_id in profile.skill_levels:
            coverage, how = ONE, "profile"
        else:
            related = [relations.get((skill.skill_id, owned)) for owned in profile.skill_levels]
            coverage, how = ZERO, "missing"
            if "equivalent" in related:
                coverage, how = HALF, "equivalent"
            elif "related" in related:
                coverage, how = Fraction(1, 4), "related"
        earned += weight * coverage
        total += weight
        detail.append(
            {
                "skill": skill.name,
                "importance": skill.importance,
                "coverage": str(coverage),
                "how": how,
            }
        )
    return _scored(earned / total, {"skills": detail}, "Weighted coverage of the required skills.")


def _remote(job: JobAttributes, intent: IntentView, gates: list[Gate], mode: Fraction) -> _Raw:
    evidence: dict[str, Any] = {
        "job_quote": _quote(job, "remote_regions"),
        "job_regions": job.remote_regions,
        "your_regions": intent.remote_regions,
    }
    if job.source_places:
        # Evidence only (ADR-069): what the board says next to what the text says.
        evidence["source_places"] = list(job.source_places)
        evidence["text_regions"] = list(job.text_remote_regions or ())
    if job.remote_regions is None:
        return _scored(
            mode * _UNVERIFIED_REMOTE_FACTOR,
            evidence,
            "Remote, but the eligible regions are not stated (treated as a risk).",
        )
    overlap = regions_intersect(job.remote_regions, intent.remote_regions)
    if overlap is None:
        return _scored(
            mode * _UNVERIFIED_REMOTE_FACTOR,
            evidence,
            "Remote, but the stated regions are not recognised (treated as a risk).",
        )
    if not overlap:
        gates.append(Gate("G2", "Remote work is not open from any of your regions.", evidence))
        return _Raw("mismatch", ZERO, evidence, "Remote work is restricted to other regions.")
    return _scored(mode, evidence, "Remote work is open from your region.")


def _on_site(job: JobAttributes, intent: IntentView, gates: list[Gate], mode: Fraction) -> _Raw:
    distances: list[dict[str, Any]] = []
    unlocated = 0
    for location in job.locations:
        if location.latitude is None or location.longitude is None:
            unlocated += 1
            distances.append({"place": location.raw, "km": None})
            continue
        km = haversine_km(
            intent.base_latitude, intent.base_longitude, location.latitude, location.longitude
        )
        distances.append({"place": location.raw, "km": round(km, 1)})
    evidence = {
        "job_quote": _quote(job, "locations"),
        "locations": distances,
        "radius_km": intent.radius_km,
    }
    within = [d for d in distances if d["km"] is not None and d["km"] <= intent.radius_km]
    if within:
        return _scored(mode, evidence, "A job location is within your distance.")
    if unlocated or not distances:
        return _unknown("The job's location could not be placed on the map.", **evidence)
    gates.append(Gate("G2", "Every job location is outside your distance.", evidence))
    return _Raw("mismatch", ZERO, evidence, "All job locations are too far away.")


def _unstated_arrangement(job: JobAttributes, intent: IntentView, gates: list[Gate]) -> _Raw:
    """Score an unstated arrangement: unknown, unless every placed office is out of reach (ADR-058).

    A posting that lists only far offices and never mentions remote work cannot be done from the
    owner's place, so gate G2 fires. Unplaced locations and a missing list stay unknown.
    """
    scratch: list[Gate] = []
    _on_site(job, intent, scratch, ONE)
    if scratch:
        evidence = scratch[0].evidence
        reason = (
            "Every job location is outside your distance and the posting does not say "
            "it can be done remotely."
        )
        gates.append(Gate("G2", reason, evidence))
        return _unknown(reason, **evidence)
    return _unknown("The work arrangement is not stated.")


def _arrangement(job: JobAttributes, intent: IntentView, gates: list[Gate]) -> _Raw:
    mode = job.work_mode
    if mode is None:
        return _unstated_arrangement(job, intent, gates)
    stance = _stance(intent, "work_arrangements", mode)
    if stance == "rejected":
        gates.append(
            Gate(
                "G2",
                f"You rejected {mode} work.",
                {"mode": mode, "job_quote": _quote(job, "work_mode")},
            )
        )
        return _Raw(
            "mismatch", ZERO, {"mode": mode, "stance": stance}, "This arrangement is rejected."
        )
    strength = _STANCE[stance] if stance else ZERO
    if mode == "remote":
        return _remote(job, intent, gates, strength)
    return _on_site(job, intent, gates, strength)


def _engagement(job: JobAttributes, intent: IntentView, gates: list[Gate]) -> _Raw:
    if not job.employment_types:
        return _unknown("The engagement type is not stated.")
    strength, all_rejected, stances = _best_stance(intent, "engagement_types", job.employment_types)
    evidence = {
        "job_quote": _quote(job, "employment_types"),
        "compared": stances,
        "hours": job.hours,
    }
    if all_rejected:
        gates.append(Gate("G3", "Every engagement type offered is one you rejected.", evidence))
        return _Raw("mismatch", ZERO, evidence, "All engagement types are rejected.")
    hours = ONE
    if job.hours == "part_time":
        if intent.part_time == "rejected":
            gates.append(
                Gate("G3", "The job is part-time and you rejected part-time work.", evidence)
            )
        hours = _STANCE[intent.part_time]
    return _scored(min(strength, hours), evidence, "Best engagement type, limited by the hours.")


def _pay_form(job: JobAttributes) -> str | None:
    """Which of the owner's pay expectations applies: ``employee`` or ``contractor``."""
    types = job.employment_types or ()
    employee = any(t.startswith("employee") for t in types)
    contractor = any(t in {"contractor_b2b", "freelance"} for t in types)
    if employee != contractor:
        return "employee" if employee else "contractor"
    if job.pay is None:
        return None
    return "employee" if job.pay.form == "annual_salary" else "contractor"


def _compensation(job: JobAttributes, intent: IntentView, gates: list[Gate]) -> _Raw:
    pay = job.pay
    if pay is None:
        return _unknown("The posting does not state pay.")
    form = _pay_form(job)
    expectation: PayExpectation | None = (
        intent.employee_pay if form == "employee" else intent.contractor_pay
    )
    if expectation is None:
        return _unknown("You have not set a pay expectation for this kind of work.")
    if pay.currency != expectation.currency:
        return _unknown(
            "The pay is in another currency (conversion is not supported yet).",
            job_currency=pay.currency,
            your_currency=expectation.currency,
        )
    assumptions: list[str] = []
    factor = Fraction(1)
    if form == "employee":
        if pay.form != "annual_salary":
            return _unknown("The pay is not an annual salary and cannot be compared.")
        if pay.period == "month":
            factor = Fraction(expectation.payments_per_year)
            assumptions.append(f"monthly pay x {expectation.payments_per_year} payments per year")
    else:
        if pay.form == "annual_salary":
            return _unknown("An annual salary cannot be compared with a day rate.")
        if pay.form == "hourly_rate":
            factor = Fraction(_HOURS_PER_DAY)
            assumptions.append(f"hourly pay x {_HOURS_PER_DAY} hours per day")
    low, high = Fraction(pay.minimum) * factor, Fraction(pay.maximum) * factor
    mid = (low + high) / 2
    minimum, target = Fraction(expectation.minimum), Fraction(expectation.target)
    evidence = {
        "job_quote": _quote(job, "compensation"),
        "job_range": [float(low), float(high)],
        "your_minimum": float(minimum),
        "your_target": float(target),
        "assumptions": assumptions,
    }
    if high < minimum:
        if intent.reject_below_minimum:
            gates.append(Gate("G10", "The stated pay is below your minimum.", evidence))
        return _Raw("mismatch", ZERO, evidence, "The stated pay is below your minimum.")
    if mid >= target:
        return _scored(ONE, evidence, "The stated pay reaches your target.")
    if mid <= minimum:
        return _scored(Fraction(1, 4), evidence, "The stated pay only just reaches your minimum.")
    strength = Fraction(1, 4) + Fraction(3, 4) * (mid - minimum) / (target - minimum)
    return _scored(strength, evidence, "The stated pay lies between your minimum and target.")


def _seniority(job: JobAttributes, intent: IntentView, gates: list[Gate]) -> _Raw:
    if not job.seniority_levels:
        return _unknown("The seniority is not stated.")
    strength, all_rejected, stances = _best_stance(intent, "seniority_levels", job.seniority_levels)
    evidence = {"job_quote": _quote(job, "seniority_levels"), "compared": stances}
    if all_rejected:
        gates.append(Gate("G4", "Every level the job allows is one you rejected.", evidence))
        return _Raw("mismatch", ZERO, evidence, "All allowed levels are rejected.")
    return _scored(strength, evidence, "Best stance among the levels the job allows.")


def _single(
    job: JobAttributes,
    intent: IntentView,
    gates: list[Gate],
    *,
    value: str | None,
    group: str,
    attribute: str,
    code: str,
    label: str,
) -> _Raw:
    if value is None:
        return _unknown(f"The {label} is not stated.")
    stance = _stance(intent, group, value)
    evidence = {"job_quote": _quote(job, attribute), "compared": {value: stance}}
    if stance == "rejected":
        gates.append(Gate(code, f"You rejected this {label}.", evidence))
        return _Raw("mismatch", ZERO, evidence, f"The {label} is rejected.")
    if stance is None:
        return _Raw("mismatch", ZERO, evidence, f"The {label} is not one you listed.")
    return _scored(_STANCE[stance], evidence, f"The {label} matches your stance.")


def _benefits(job: JobAttributes, intent: IntentView) -> _Raw:
    if not intent.benefits_wanted:
        return _unknown("You have not chosen benefits you want.")
    if not job.benefits_mentioned:
        return _unknown("The posting states no benefits.")
    mentioned = {b.casefold() for b in job.benefits_mentioned}
    hits = [b for b in intent.benefits_wanted if b.casefold() in mentioned]
    evidence = {
        "job_quote": _quote(job, "benefits_mentioned"),
        "wanted": intent.benefits_wanted,
        "found": hits,
    }
    return _scored(
        Fraction(len(hits), len(intent.benefits_wanted)),
        evidence,
        "Share of the benefits you want.",
    )


def _education(job: JobAttributes, profile: ProfileView) -> _Raw:
    """Compare the education the posting requires with the profile's."""
    required = job.education_required
    if not required:
        return _unknown("The posting states no education requirement.")
    needed = _EDUCATION_RANK.get(normalise_place(required).replace(" ", ""))
    if needed is None:
        return _unknown("The education requirement is not recognised.", required=required)
    held = max(
        (
            _EDUCATION_RANK.get(normalise_place(e).replace(" ", ""), 0)
            for e in profile.education_levels
        ),
        default=0,
    )
    evidence = {
        "job_quote": _quote(job, "education_required"),
        "required": required,
        "yours": profile.education_levels,
    }
    if held >= needed:
        return _scored(ONE, evidence, "Your education meets the requirement.")
    return _Raw("mismatch", ZERO, evidence, "Your education is below the requirement.")


_CREDENTIAL_WEIGHT = {"must": 2, "nice": 1}


def _credentials(job: JobAttributes, profile: ProfileView) -> _Raw:
    """Share of the licences and certifications the posting asks for that the owner holds.

    A required one weighs 2 and a preferred one 1, as for skills. There is no judging of near
    equivalents: a licence is held or it is not.
    """
    if not job.credentials:
        return _unknown("The posting names no licence or certification.")
    total = sum(_CREDENTIAL_WEIGHT[c.importance] for c in job.credentials)
    covered = sum(
        _CREDENTIAL_WEIGHT[c.importance]
        for c in job.credentials
        if c.skill_id in profile.credential_ids
    )
    evidence = {
        "job_quote": _quote(job, "credentials"),
        "credentials": [
            {
                "name": c.name,
                "importance": c.importance,
                "held": c.skill_id in profile.credential_ids,
            }
            for c in job.credentials
        ],
    }
    strength = Fraction(covered, total)
    status: Status = "match" if strength > 0 else "mismatch"
    return _Raw(
        status, strength, evidence, "Share of the required licences and certifications you hold."
    )


def _qualifications(job: JobAttributes, profile: ProfileView) -> _Raw:
    """Education and credentials together: the mean of the parts the posting states."""
    education = _education(job, profile)
    if not job.credentials:
        return education  # exactly what this dimension was before credentials existed
    credentials = _credentials(job, profile)
    parts = [part for part in (education, credentials) if part.strength is not None]
    strength = sum((part.strength for part in parts if part.strength is not None), ZERO) / len(
        parts
    )
    evidence: dict[str, Any] = {}
    for part in parts:
        evidence.update(part.evidence)
    status: Status = "match" if strength > 0 else "mismatch"
    explanation = " ".join(part.explanation for part in parts)
    return _Raw(status, strength, evidence, explanation)


def _direction(job: JobAttributes) -> _Raw:
    """Score the best judged career direction; the choice is made here, never by the model."""
    if not job.directions:
        return _unknown("The job was not assessed against your career directions.")
    known = [j for j in job.directions if j.level in _DIRECTION_STRENGTH]
    if not known:
        return _unknown("No career direction could be judged for this job.")
    best = max(known, key=lambda j: _DIRECTION_STRENGTH[j.level])
    evidence = {
        "direction": best.label,
        "level": best.level,
        "job_quote": best.job_quote,
        "direction_quote": best.direction_quote,
        "judged": {j.label: j.level for j in job.directions},
    }
    return _scored(
        _DIRECTION_STRENGTH[best.level], evidence, f"Best fit among your directions: {best.label}."
    )


# --- gates that do not belong to one dimension ---------------------------------------------


def _extra_gates(job: JobAttributes, intent: IntentView, profile: ProfileView) -> list[Gate]:
    gates: list[Gate] = []
    if intent.reject_unspoken_required and job.languages_required:
        missing = sorted(
            code for code in job.languages_required if code.lower() not in intent.can_work_in
        )
        if missing:
            gates.append(
                Gate(
                    "G7",
                    "The job requires a language you do not work in.",
                    {"missing": missing, "job_quote": _quote(job, "languages_required")},
                )
            )
    company = normalise_place(job.company_name)
    if company and company in {normalise_place(name) for name in intent.excluded_companies}:
        gates.append(
            Gate("G8", "The company is on your ignore list.", {"company": job.company_name})
        )
    haystack = f"{job.title}\n{job.description}"
    hits = [
        word
        for word in intent.excluded_words
        if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", haystack, re.IGNORECASE)
    ]
    if hits:
        gates.append(Gate("G9", "The posting contains a word you excluded.", {"words": hits}))
    if intent.reject_missing_credentials:
        missing = [
            c.name
            for c in job.credentials
            if c.importance == "must" and c.skill_id not in profile.credential_ids
        ]
        if missing:
            gates.append(
                Gate(
                    "G12",
                    "The job requires a licence or certification you do not hold.",
                    {"missing": missing, "job_quote": _quote(job, "credentials")},
                )
            )
    if intent.needs_visa and job.visa_sponsorship is False:
        gates.append(
            Gate(
                "G11",
                "You need visa or relocation help and the posting says it is not offered.",
                {"job_quote": _quote(job, "visa_sponsorship")},
            )
        )
    return gates


# --- scoring -----------------------------------------------------------------------------------


def _quality(strength: Fraction | None, status: Status) -> Quality | None:
    if status != "match" or strength is None:
        return None
    if strength >= Fraction(3, 4):
        return "strong"
    return "partial" if strength >= Fraction(1, 4) else "weak"


def _decimal(value: Fraction, places: str) -> Decimal:
    exact = Decimal(value.numerator) / Decimal(value.denominator)
    return exact.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def band_of(score: int, *, gated: bool = False) -> str:
    """Return the quality band of a score; a gated job is ``not_recommended`` whatever its score."""
    if gated:
        return "not_recommended"
    if score >= 80:
        return "excellent"
    if score >= 65:
        return "strong"
    return "average" if score >= 45 else "low"


def evaluate(
    job: JobAttributes,
    profile: ProfileView,
    intent: IntentView,
    relations: SkillRelations,
) -> Evaluation:
    """Score ``job`` for one profile and intent with the rules of ``matching-v1``.

    Raises:
        ValueError: if every weight is 0, because nothing could be scored.
    """
    weights = {key: intent.weights.get(key, 0) for key in DIMENSION_KEYS}
    if not job.directions:
        weights["career_direction"] = 0  # not assessed: left out instead of counting as 0
    total = sum(weights.values())
    if total <= 0:
        msg = "at least one weight must be above 0"
        raise ValueError(msg)

    gates: list[Gate] = []
    raws: dict[str, _Raw] = {
        "role_responsibilities": _role(job, intent, gates),
        "skills_technology": _skills(job, profile, relations),
        "work_arrangement_location": _arrangement(job, intent, gates),
        "engagement_terms": _engagement(job, intent, gates),
        "compensation": _compensation(job, intent, gates),
        "seniority_experience": _seniority(job, intent, gates),
        "domain_sector": _single(
            job,
            intent,
            gates,
            value=job.sector_primary,
            group="sectors",
            attribute="sectors",
            code="G5",
            label="primary sector",
        ),
        "company_profile": _single(
            job,
            intent,
            gates,
            value=job.employer_type,
            group="employer_types",
            attribute="employer_type",
            code="G6",
            label="employer type",
        ),
        "benefits_flexibility": _benefits(job, intent),
        "qualifications": _qualifications(job, profile),
        "career_direction": _direction(job),
    }
    gates.extend(_extra_gates(job, intent, profile))

    results: list[DimensionResult] = []
    for key in DIMENSION_KEYS:
        raw, weight = raws[key], weights[key]
        share = Fraction(weight * 100, total)
        contribution = share * raw.strength if raw.strength is not None else ZERO
        results.append(
            DimensionResult(
                key=key,
                status=raw.status,
                quality=_quality(raw.strength, raw.status),
                weight=weight,
                effective_weight=_decimal(share, "0.01"),
                strength=_decimal(raw.strength, "0.0001") if raw.strength is not None else None,
                contribution=_decimal(contribution, "0.1"),
                excluded=weight == 0,
                evidence=raw.evidence,
                explanation=raw.explanation,
            )
        )
    score = int(
        sum((r.contribution for r in results), Decimal(0)).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )
    score = max(0, min(100, score))
    gated = bool(gates)
    return Evaluation(
        policy_version=POLICY_VERSION,
        fit_score=score,
        band=band_of(score, gated=gated),
        recommendation="not_recommended" if gated else "recommended",
        gates=tuple(gates),
        dimensions=tuple(results),
    )
