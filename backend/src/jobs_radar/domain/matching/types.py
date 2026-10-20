"""Inputs and outputs of the matching engine (document 13, section 7).

Plain frozen dataclasses with no dependency on the API schemas, the database or any provider, so
the engine stays a pure function. A mapper in the service layer builds these from stored data.
``None`` means *not stated or not verified*: the engine never guesses it.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

Stance = Literal["preferred", "acceptable", "rejected"]
Status = Literal["match", "mismatch", "unknown"]
Quality = Literal["strong", "partial", "weak"]
# How well a job fits one of the owner's career directions, as judged by the local model (ADR-057).
DirectionLevel = Literal["strong", "partial", "weak", "none", "unknown"]

# Intent groups that carry stances (the keys of ``IntentView.stances``).
GROUPS = (
    "role_families",
    "work_arrangements",
    "engagement_types",
    "seniority_levels",
    "sectors",
    "employer_types",
)
DIMENSION_KEYS = (
    "role_responsibilities",
    "skills_technology",
    "work_arrangement_location",
    "engagement_terms",
    "compensation",
    "seniority_experience",
    "domain_sector",
    "company_profile",
    "benefits_flexibility",
    "qualifications",
    "career_direction",
)


@dataclass(frozen=True)
class JobLocation:
    """A place named by the job; coordinates are ``None`` when it could not be resolved."""

    raw: str
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class JobPay:
    """Pay exactly as stated in the posting."""

    form: Literal["annual_salary", "day_rate", "hourly_rate"]
    currency: str
    minimum: float
    maximum: float
    period: Literal["year", "month", "day", "hour"]


@dataclass(frozen=True)
class JobSkill:
    """A required (``must``) or preferred (``nice``) skill, already mapped to a canonical skill."""

    skill_id: int
    name: str
    importance: Literal["must", "nice"]


@dataclass(frozen=True)
class DirectionJudgement:
    """The stored judgement of one career direction against a job (ADR-057)."""

    label: str
    level: DirectionLevel
    job_quote: str | None = None
    direction_quote: str | None = None


@dataclass(frozen=True)
class JobAttributes:
    """What the extraction established about a job. Missing information is ``None`` or empty."""

    title: str
    description: str
    company_name: str
    role_families: tuple[tuple[str, float], ...] = ()
    work_mode: str | None = None
    remote_regions: tuple[str, ...] | None = None
    # Evidence only (ADR-069): the places the board states and the regions the model read from the
    # text, before the places limited them. Neither changes the score.
    text_remote_regions: tuple[str, ...] | None = None
    source_places: tuple[str, ...] = ()
    locations: tuple[JobLocation, ...] = ()
    employment_types: tuple[str, ...] | None = None
    hours: str | None = None
    pay: JobPay | None = None
    seniority_levels: tuple[str, ...] | None = None
    sector_primary: str | None = None
    skills: tuple[JobSkill, ...] = ()
    # Licences and certifications the posting asks for, mapped to canonical skills (ADR-080).
    credentials: tuple[JobSkill, ...] = ()
    languages_required: tuple[str, ...] | None = None
    employer_type: str | None = None
    education_required: str | None = None
    benefits_mentioned: tuple[str, ...] | None = None
    visa_sponsorship: bool | None = None
    # Verbatim quotes from the posting, by attribute name (used in the evidence of each result).
    evidence: Mapping[str, str] = field(default_factory=dict)
    # One judgement per enabled career direction; ``None`` means the job was not assessed, which
    # leaves the dimension out (an assessed but unclear job is ``unknown`` and counts as 0).
    directions: tuple[DirectionJudgement, ...] | None = None


@dataclass(frozen=True)
class ProfileView:
    """The facts of a profile revision that matching needs."""

    skill_levels: Mapping[int, str] = field(default_factory=dict)
    languages: frozenset[str] = frozenset()
    education_levels: tuple[str, ...] = ()
    certifications: tuple[str, ...] = ()
    # Skills of the profile that are licences or certifications (ADR-080).
    credential_ids: frozenset[int] = frozenset()


@dataclass(frozen=True)
class PayExpectation:
    """The owner's minimum and target; annual for employees, per day for contractors."""

    currency: str
    minimum: float
    target: float
    payments_per_year: int = 14


@dataclass(frozen=True)
class IntentView:
    """The parts of an intent revision that matching needs."""

    stances: Mapping[str, Mapping[str, Stance]]
    part_time: Stance = "acceptable"
    remote_regions: tuple[str, ...] = ()
    base_latitude: float = 0.0
    base_longitude: float = 0.0
    radius_km: int = 40
    employee_pay: PayExpectation | None = None
    contractor_pay: PayExpectation | None = None
    reject_below_minimum: bool = True
    can_work_in: frozenset[str] = frozenset()
    reject_unspoken_required: bool = True
    excluded_companies: tuple[str, ...] = ()
    excluded_words: tuple[str, ...] = ()
    needs_visa: bool = False
    # Rule out jobs that require a licence or certification the owner does not hold (G12, off).
    reject_missing_credentials: bool = False
    benefits_wanted: tuple[str, ...] = ()
    weights: Mapping[str, int] = field(default_factory=dict)


# (job skill id, profile skill id) -> "equivalent" | "related" (anything else counts as unrelated)
SkillRelations = Mapping[tuple[int, int], str]


@dataclass(frozen=True)
class Gate:
    """A hard constraint that fired, with its reason and the evidence behind it."""

    code: str
    reason: str
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DimensionResult:
    """How one dimension scored. ``strength`` is ``None`` when the status is unknown."""

    key: str
    status: Status
    quality: Quality | None
    weight: int
    effective_weight: Decimal
    strength: Decimal | None
    contribution: Decimal
    excluded: bool
    evidence: Mapping[str, Any]
    explanation: str


@dataclass(frozen=True)
class Evaluation:
    """The result of ``matching-v1`` for one job under one profile and one intent."""

    policy_version: str
    fit_score: int
    band: str
    recommendation: Literal["recommended", "not_recommended"]
    gates: tuple[Gate, ...]
    dimensions: tuple[DimensionResult, ...]
