"""Search Intent contract and validation rules (document 13, section 4; ADR-024, ADR-026)."""

from collections.abc import Mapping
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from jobs_radar.domain.enums import Stance
from jobs_radar.schemas.common import (
    CurrencyCode,
    IanaTimezone,
    LanguageCode,
    Latitude,
    Longitude,
    Money,
    RegionCode,
    StrictModel,
    TaxonomyKey,
)


class StanceEntry(StrictModel):
    """The owner's stance on one taxonomy term."""

    key: TaxonomyKey
    stance: Stance


def _check_group(name: str, entries: list[StanceEntry]) -> list[StanceEntry]:
    keys = [entry.key for entry in entries]
    if len(keys) != len(set(keys)):
        msg = f"{name}: duplicate key"
        raise ValueError(msg)
    # An intent where everything is rejected can never match anything (incoherent, UC-03).
    if not any(entry.stance is not Stance.REJECTED for entry in entries):
        msg = f"{name}: at least one option must not be rejected"
        raise ValueError(msg)
    return entries


class HoursStances(StrictModel):
    """Stance on working hours that are not full time."""

    part_time: Stance = Stance.ACCEPTABLE


class Stances(StrictModel):
    """Preferred, acceptable or rejected for every option group."""

    role_families: list[StanceEntry]
    work_arrangements: list[StanceEntry]
    engagement_types: list[StanceEntry]
    hours: HoursStances = HoursStances()
    seniority_levels: list[StanceEntry]
    sectors: list[StanceEntry] = Field(default_factory=list)
    employer_types: list[StanceEntry]

    @field_validator(
        "role_families",
        "work_arrangements",
        "engagement_types",
        "seniority_levels",
        "employer_types",
    )
    @classmethod
    def _required_groups(cls, entries: list[StanceEntry], info: object) -> list[StanceEntry]:
        return _check_group(getattr(info, "field_name", "group"), entries)

    @field_validator("sectors")
    @classmethod
    def _sectors(cls, entries: list[StanceEntry]) -> list[StanceEntry]:
        # No sector preference at all is legitimate; a non-empty list must still be coherent.
        return _check_group("sectors", entries) if entries else entries


class RemoteRule(StrictModel):
    """Where remote work is acceptable from."""

    eligible_regions: list[RegionCode] = Field(min_length=1)
    timezone: IanaTimezone
    timezone_tolerance_hours: int | None = Field(default=None, ge=0, le=12)


class OnsiteHybridRule(StrictModel):
    """How far from a base place hybrid and on-site work may be."""

    base_place: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    latitude: Latitude
    longitude: Longitude
    radius_km: int = Field(ge=1, le=500)


class WorkRules(StrictModel):
    """Place rules per work arrangement."""

    remote: RemoteRule
    onsite_hybrid: OnsiteHybridRule


class EmployeePay(StrictModel):
    """Employee pay expectations. The annual amount is canonical; monthly is derived (D9)."""

    currency: CurrencyCode
    payments_per_year: Literal[12, 14]
    annual_minimum: Money
    annual_target: Money

    @model_validator(mode="after")
    def _target_not_below_minimum(self) -> Self:
        if self.annual_target < self.annual_minimum:
            msg = "annual_target must not be below annual_minimum"
            raise ValueError(msg)
        return self

    @property
    def monthly_minimum(self) -> float:
        """Minimum per payment (annual minimum divided by 12 or 14)."""
        return self.annual_minimum / self.payments_per_year

    @property
    def monthly_target(self) -> float:
        """Target per payment (annual target divided by 12 or 14)."""
        return self.annual_target / self.payments_per_year


class ContractorRate(StrictModel):
    """Contractor and freelance pay expectation: a day rate only."""

    currency: CurrencyCode
    minimum: Money
    target: Money

    @model_validator(mode="after")
    def _target_not_below_minimum(self) -> Self:
        if self.target < self.minimum:
            msg = "target must not be below minimum"
            raise ValueError(msg)
        return self


class Compensation(StrictModel):
    """Pay expectations per engagement form."""

    employee_pay: EmployeePay | None = None
    contractor_day_rate: ContractorRate | None = None
    reject_below_minimum: bool = True


class LanguagePreferences(StrictModel):
    """Languages the owner can work in."""

    can_work_in: list[LanguageCode] = Field(min_length=1)
    reject_unspoken_required: bool = True


class Exclusions(StrictModel):
    """Companies and words that rule a job out."""

    companies: list[Annotated[str, StringConstraints(min_length=1, max_length=200)]] = Field(
        default_factory=list, max_length=100
    )
    words: list[Annotated[str, StringConstraints(min_length=1, max_length=60)]] = Field(
        default_factory=list, max_length=100
    )


class Filters(StrictModel):
    """Optional filters that are not scored."""

    max_posting_age_days: int | None = Field(default=None, ge=1, le=365)
    needs_visa_or_relocation: bool = False


Weight = Annotated[int, Field(ge=0, le=40)]


class Weights(StrictModel):
    """One relative weight per dimension. The optional dimensions default to 0 (excluded)."""

    role_responsibilities: Weight = 25
    skills_technology: Weight = 15
    work_arrangement_location: Weight = 15
    engagement_terms: Weight = 10
    compensation: Weight = 10
    seniority_experience: Weight = 8
    domain_sector: Weight = 10
    company_profile: Weight = 7
    benefits_flexibility: Weight = 0
    qualifications: Weight = 0
    # Optional like the two above; 0 leaves the career directions out of the score (ADR-057).
    career_direction: Weight = 0

    @model_validator(mode="after")
    def _at_least_one_weight(self) -> Self:
        if sum(self.model_dump().values()) == 0:
            msg = "at least one weight must be above 0"
            raise ValueError(msg)
        return self


Keyword = Annotated[str, StringConstraints(min_length=1, max_length=60)]


class IntentDefinition(StrictModel):
    """The content of one immutable intent revision."""

    schema_version: Literal[1] = 1
    title: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    stances: Stances
    work_rules: WorkRules
    compensation: Compensation = Compensation()
    languages: LanguagePreferences
    keywords: list[Keyword] = Field(default_factory=list, max_length=50)
    exclusions: Exclusions = Exclusions()
    filters: Filters = Filters()
    benefits_wanted: list[TaxonomyKey] = Field(default_factory=list)
    weights: Weights = Weights()
    alert_threshold: int = Field(default=65, ge=0, le=100)


# Intent group -> taxonomy kind; the closed groups must list every term of their kind.
_GROUP_KINDS = {
    "role_families": "role_family",
    "work_arrangements": "work_arrangement",
    "engagement_types": "engagement_type",
    "seniority_levels": "seniority_level",
    "sectors": "sector",
    "employer_types": "employer_type",
}
_OPEN_GROUPS = {"role_families", "sectors"}


def validate_intent_against_taxonomy(
    intent: IntentDefinition, taxonomy: Mapping[str, set[str]]
) -> list[str]:
    """Check the intent against the live taxonomy; returns human-readable errors (empty if valid).

    Every key must exist, and the closed groups (everything except role families and sectors) must
    list every term so that no option silently falls back to a default.
    """
    errors: list[str] = []
    for group, kind in _GROUP_KINDS.items():
        entries: list[StanceEntry] = getattr(intent.stances, group)
        known = taxonomy.get(kind, set())
        listed = {entry.key for entry in entries}
        errors.extend(f"{group}: unknown key '{key}'" for key in sorted(listed - known))
        if group not in _OPEN_GROUPS and (missing := sorted(known - listed)):
            errors.append(f"{group}: missing options: {', '.join(missing)}")
    benefits = taxonomy.get("benefit", set())
    errors.extend(
        f"benefits_wanted: unknown key '{key}'"
        for key in sorted(set(intent.benefits_wanted) - benefits)
    )
    return errors
