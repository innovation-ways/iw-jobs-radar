"""Output contract of the AI extraction step (document 13, section 6; ADR-021, ADR-027).

The model must return this object. Every attribute carries a confidence and a verbatim quote from
the job description; a known attribute without a quote is invalid. Verifying that a quote really
occurs in the description is done by the extraction service (task T4).
"""

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from jobs_radar.schemas.common import (
    CurrencyCode,
    LanguageCode,
    Money,
    Probability,
    StrictModel,
    TaxonomyKey,
)
from jobs_radar.schemas.job import FactStatus

Quote = Annotated[str, StringConstraints(min_length=1)]


class Evidenced[T](StrictModel):
    """An attribute with its status, confidence and supporting quote."""

    value: T | None
    status: FactStatus
    confidence: Probability
    evidence: str | None = None

    @classmethod
    def unknown(cls) -> Self:
        """Return the 'not stated' attribute."""
        return cls(value=None, status="unknown", confidence=0.0, evidence=None)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.status == "unknown" and self.value is not None:
            msg = "an unknown attribute must not carry a value"
            raise ValueError(msg)
        if self.status == "known":
            if self.value is None:
                msg = "a known attribute needs a value"
                raise ValueError(msg)
            if not self.evidence:
                msg = "a known attribute must quote its evidence"
                raise ValueError(msg)
        return self


class ExtractedCompensation(StrictModel):
    """Pay exactly as stated in the posting."""

    form: Literal["annual_salary", "day_rate", "hourly_rate"]
    currency: CurrencyCode
    min: Money
    max: Money
    period: Literal["year", "month", "day", "hour"]
    disclosed: bool = True


class ExtractedSectors(StrictModel):
    """Primary and secondary sector keys."""

    primary: TaxonomyKey
    secondary: list[TaxonomyKey] = Field(default_factory=list)


class ExtractedLanguage(StrictModel):
    """A language requirement."""

    language: LanguageCode
    level: str | None = None


class ExtractedRoleFamily(StrictModel):
    """A role family with confidence and a quote."""

    key: TaxonomyKey
    confidence: Probability
    evidence: Quote


class ExtractedSkill(StrictModel):
    """A skill mention (by name; canonicalisation happens later) with a quote."""

    name: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    importance: Literal["must", "nice"]
    evidence: Quote


class ExtractionOutput(StrictModel):
    """What the model must return for one job description."""

    schema_version: Literal[1] = 1
    title: Evidenced[str]
    employment_types: Evidenced[list[TaxonomyKey]]
    hours: Evidenced[Literal["full_time", "part_time"]]
    work_mode: Evidenced[Literal["remote", "hybrid", "onsite"]]
    remote_regions: Evidenced[list[str]]
    locations: Evidenced[list[str]]
    compensation: Evidenced[ExtractedCompensation]
    seniority_levels: Evidenced[list[TaxonomyKey]]
    years_required_min: Evidenced[int] = Field(default_factory=Evidenced[int].unknown)
    role_families: list[ExtractedRoleFamily] = Field(default_factory=list)
    sectors: Evidenced[ExtractedSectors]
    skills: list[ExtractedSkill] = Field(default_factory=list)
    languages_required: Evidenced[list[ExtractedLanguage]]
    employer_type: Evidenced[TaxonomyKey]
    education_required: Evidenced[str]
    benefits_mentioned: Evidenced[list[TaxonomyKey]]
    visa_sponsorship: Evidenced[bool]
