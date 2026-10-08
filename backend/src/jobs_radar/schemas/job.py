"""Normalised job contract (document 13, section 5).

Every attribute is a fact with a status: ``known`` (value present) or ``unknown`` (never guessed,
ADR-005). Names follow schema.org ``JobPosting`` where an equivalent exists.
"""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from jobs_radar.domain.enums import SourceType
from jobs_radar.schemas.common import (
    CountryCode,
    CurrencyCode,
    LanguageCode,
    Latitude,
    Longitude,
    Money,
    Probability,
    RegionCode,
    StrictModel,
    TaxonomyKey,
)

FactStatus = Literal["known", "unknown"]


class ValueFact(StrictModel):
    """A single value that is either known or explicitly unknown."""

    value: str | None
    status: FactStatus

    @model_validator(mode="after")
    def _value_matches_status(self) -> Self:
        if self.status == "known" and self.value is None:
            msg = "a known fact needs a value"
            raise ValueError(msg)
        if self.status == "unknown" and self.value is not None:
            msg = "an unknown fact must not carry a value"
            raise ValueError(msg)
        return self


class Employment(StrictModel):
    """Engagement types the posting allows and the working hours."""

    types: list[ValueFact] = Field(default_factory=list)
    hours: ValueFact


class RemoteEligibility(StrictModel):
    """Where a remote worker may be located."""

    status: FactStatus
    anywhere: bool = False
    regions: list[RegionCode] = Field(default_factory=list)
    countries: list[CountryCode] = Field(default_factory=list)
    timezone_offset_range_hours: tuple[int, int] | None = None

    @model_validator(mode="after")
    def _offsets_are_ordered(self) -> Self:
        if self.timezone_offset_range_hours is not None:
            low, high = self.timezone_offset_range_hours
            if low > high or low < -12 or high > 14:
                msg = "timezone_offset_range_hours must be ordered and within -12..14"
                raise ValueError(msg)
        return self


class Location(StrictModel):
    """A location as written in the posting plus its resolved parts."""

    raw: str
    country: Annotated[str, StringConstraints(pattern=r"^([A-Z]{2})?$")] = ""
    region: str = ""
    city: str = ""
    latitude: Latitude | None = None
    longitude: Longitude | None = None


class WorkArrangement(StrictModel):
    """Remote, hybrid or on-site, plus eligibility and locations."""

    mode: ValueFact
    remote_eligibility: RemoteEligibility
    locations: list[Location] = Field(default_factory=list)


class UnknownCompensation(StrictModel):
    """Pay is not stated."""

    status: Literal["unknown"]


class KnownCompensation(StrictModel):
    """Pay as stated; the evaluator applies conversions later and records them in assumptions."""

    status: Literal["known"]
    form: Literal["annual_salary", "day_rate", "hourly_rate"]
    currency: CurrencyCode
    min: Money
    max: Money
    period: Literal["year", "month", "day", "hour"]
    disclosed: bool
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _max_not_below_min(self) -> Self:
        if self.max < self.min:
            msg = "max must not be below min"
            raise ValueError(msg)
        return self


Compensation = Annotated[UnknownCompensation | KnownCompensation, Field(discriminator="status")]


class Seniority(StrictModel):
    """Levels the posting allows and the minimum years asked for."""

    levels: list[TaxonomyKey] = Field(default_factory=list)
    years_required_min: int | None = Field(default=None, ge=0, le=60)
    status: FactStatus


class RoleFamilyScore(StrictModel):
    """A role family the posting belongs to, with the extractor's confidence."""

    key: TaxonomyKey
    confidence: Probability


class Sectors(StrictModel):
    """Primary and secondary sectors."""

    primary: TaxonomyKey | None = None
    secondary: list[TaxonomyKey] = Field(default_factory=list)
    status: FactStatus


class JobSkill(StrictModel):
    """A skill the posting asks for."""

    skill_id: int
    importance: Literal["must", "nice"]


class JobSkills(StrictModel):
    """Required and preferred skills."""

    required: list[JobSkill] = Field(default_factory=list)
    preferred: list[JobSkill] = Field(default_factory=list)


class LanguageRequirement(StrictModel):
    """A language the posting requires."""

    language: LanguageCode
    level: str | None = None


class Employer(StrictModel):
    """The company and the kind of employer."""

    company_id: int
    type: ValueFact


class EducationRequired(StrictModel):
    """Required education level."""

    level: str | None = None
    status: FactStatus


class VisaSponsorship(StrictModel):
    """Whether the employer offers visa sponsorship."""

    status: FactStatus
    offered: bool | None = None

    @model_validator(mode="after")
    def _offered_matches_status(self) -> Self:
        if self.status == "known" and self.offered is None:
            msg = "a known visa statement needs 'offered'"
            raise ValueError(msg)
        return self


class SourceInfo(StrictModel):
    """Provenance of the posting."""

    source_type: SourceType
    external_job_id: str
    url: str
    apply_url: str | None = None
    language: str | None = None


class NormalisedJob(StrictModel):
    """The normalised content stored with each job snapshot."""

    schema_version: Literal[1] = 1
    title: str
    description_text: str
    employment: Employment
    work_arrangement: WorkArrangement
    compensation: Compensation
    seniority: Seniority
    role_families: list[RoleFamilyScore] = Field(default_factory=list)
    sectors: Sectors
    skills: JobSkills = JobSkills()
    languages_required: list[LanguageRequirement] = Field(default_factory=list)
    employer: Employer
    education_required: EducationRequired
    benefits_mentioned: list[TaxonomyKey] = Field(default_factory=list)
    visa_sponsorship: VisaSponsorship
    posted_at: datetime | None = None
    valid_through: datetime | None = None
    source: SourceInfo
