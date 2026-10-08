"""What the owner edits when saving a profile (skills by name, no provenance).

The service resolves skill names to canonical skills and adds provenance, producing the stored
:class:`~jobs_radar.schemas.profile.ProfileFacts`.
"""

from typing import Annotated, Self

from pydantic import Field, StringConstraints, model_validator

from jobs_radar.domain.enums import SkillKind
from jobs_radar.domain.skills import normalise_skill_name
from jobs_radar.schemas.common import StrictModel, YearMonth
from jobs_radar.schemas.profile import (
    BaseLocation,
    LanguageSkill,
    ProfilePrivacy,
    ShortText,
    SkillLevel,
)

SkillName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class SkillInput(StrictModel):
    """A skill as typed by the owner."""

    name: SkillName
    kind: SkillKind = SkillKind.TECHNOLOGY
    level: SkillLevel
    years: float = Field(ge=0, le=70)


class ExperienceInput(StrictModel):
    """A past role."""

    title: ShortText
    organisation: ShortText
    start: YearMonth
    end: YearMonth | None = None
    summary: str = ""
    sectors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _end_not_before_start(self) -> Self:
        if self.end is not None and self.end < self.start:
            msg = "end must not be before start"
            raise ValueError(msg)
        return self


class EducationInput(StrictModel):
    """A degree or similar."""

    level: ShortText
    field: ShortText


class CertificationInput(StrictModel):
    """A certification."""

    name: ShortText
    year: int | None = Field(default=None, ge=1950, le=2100)


class ProfileInput(StrictModel):
    """The editable content of a profile revision."""

    headline: ShortText
    base_location: BaseLocation
    years_experience: int = Field(ge=0, le=70)
    languages: list[LanguageSkill] = Field(default_factory=list)
    skills: list[SkillInput] = Field(default_factory=list)
    experience: list[ExperienceInput] = Field(default_factory=list)
    education: list[EducationInput] = Field(default_factory=list)
    certifications: list[CertificationInput] = Field(default_factory=list)
    privacy: ProfilePrivacy = ProfilePrivacy()

    @model_validator(mode="after")
    def _skills_are_unique(self) -> Self:
        names = [normalise_skill_name(skill.name) for skill in self.skills]
        if len(names) != len(set(names)):
            msg = "duplicate skill in skills"
            raise ValueError(msg)
        return self
