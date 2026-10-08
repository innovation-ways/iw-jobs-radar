"""Career Profile facts and privacy settings (document 13, section 3)."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from jobs_radar.domain.enums import EvidenceOrigin
from jobs_radar.schemas.common import (
    CountryCode,
    IanaTimezone,
    LanguageCode,
    Latitude,
    Longitude,
    StrictModel,
    YearMonth,
)

SkillLevel = Literal["beginner", "intermediate", "advanced", "expert"]
LanguageLevel = Literal["A1", "A2", "B1", "B2", "C1", "C2", "native"]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class Provenance(StrictModel):
    """Where a fact came from; only accepted facts exist in a revision."""

    origin: EvidenceOrigin
    evidence_id: int | None = None
    accepted_at: datetime | None = None


class BaseLocation(StrictModel):
    """Anchor for hybrid and on-site distance rules."""

    place: ShortText
    country: CountryCode
    timezone: IanaTimezone
    latitude: Latitude | None = None
    longitude: Longitude | None = None


class LanguageSkill(StrictModel):
    """A language the owner speaks and the level."""

    language: LanguageCode
    level: LanguageLevel


class ProfileSkill(StrictModel):
    """A skill (by id) with level and years."""

    skill_id: int
    level: SkillLevel
    years: float = Field(ge=0, le=70)
    provenance: Provenance


class Experience(StrictModel):
    """A past role."""

    title: ShortText
    organisation: ShortText
    start: YearMonth
    end: YearMonth | None = None
    summary: str = ""
    sectors: list[str] = Field(default_factory=list)
    provenance: Provenance

    @model_validator(mode="after")
    def _end_not_before_start(self) -> Self:
        # YYYY-MM strings sort chronologically, so a plain comparison is enough.
        if self.end is not None and self.end < self.start:
            msg = "end must not be before start"
            raise ValueError(msg)
        return self


class Education(StrictModel):
    """A degree or similar."""

    level: ShortText
    field: ShortText
    provenance: Provenance


class Certification(StrictModel):
    """A certification."""

    name: ShortText
    year: int | None = Field(default=None, ge=1950, le=2100)
    provenance: Provenance


class ProfileFacts(StrictModel):
    """The canonical facts stored in each immutable profile revision."""

    schema_version: Literal[1] = 1
    headline: ShortText
    base_location: BaseLocation
    years_experience: int = Field(ge=0, le=70)
    languages: list[LanguageSkill] = Field(default_factory=list)
    skills: list[ProfileSkill] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)

    @model_validator(mode="after")
    def _skills_are_unique(self) -> Self:
        ids = [skill.skill_id for skill in self.skills]
        if len(ids) != len(set(ids)):
            msg = "duplicate skill_id in skills"
            raise ValueError(msg)
        return self


class ProfilePrivacy(StrictModel):
    """Privacy choices that applied when a revision was created (conservative defaults)."""

    schema_version: Literal[1] = 1
    redact_contact_details: bool = True
    allow_cloud_processing: bool = False
