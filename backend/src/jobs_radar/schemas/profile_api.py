"""What the owner edits when saving a profile (skills by name, no provenance).

The service resolves skill names to canonical skills and adds provenance, producing the stored
:class:`~jobs_radar.schemas.profile.ProfileFacts`.
"""

from datetime import datetime
from typing import Annotated, Self

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from jobs_radar.domain.directions import MAX_DIRECTIONS
from jobs_radar.domain.enums import SkillKind, Visibility
from jobs_radar.domain.skills import normalise_skill_name
from jobs_radar.schemas.common import StrictModel, YearMonth
from jobs_radar.schemas.profile import (
    BaseLocation,
    CareerDirection,
    Certification,
    Education,
    Experience,
    LanguageSkill,
    ProfilePrivacy,
    Provenance,
    ShortText,
    SkillLevel,
    unique_labels,
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
    directions: Annotated[list[CareerDirection], AfterValidator(unique_labels)] = Field(
        default_factory=list, max_length=MAX_DIRECTIONS
    )
    privacy: ProfilePrivacy = ProfilePrivacy()

    @model_validator(mode="after")
    def _skills_are_unique(self) -> Self:
        names = [normalise_skill_name(skill.name) for skill in self.skills]
        if len(names) != len(set(names)):
            msg = "duplicate skill in skills"
            raise ValueError(msg)
        return self


# --- requests ---------------------------------------------------------------------------------


class ProfileCreate(StrictModel):
    """Create a blank, named profile."""

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    visibility: Visibility = Visibility.PRIVATE


class ProfileSave(ProfileInput):
    """Save as the next revision; ``expected_current_revision`` is ``null`` for the first one."""

    expected_current_revision: int | None = Field(default=None, ge=1)
    change_summary: Annotated[str, StringConstraints(max_length=300)] | None = None


class RestoreRequest(StrictModel):
    """Restore an old revision as the next one."""

    expected_current_revision: int = Field(ge=1)


# --- responses --------------------------------------------------------------------------------


class SkillRead(StrictModel):
    """A skill of a revision, with its canonical name."""

    skill_id: int
    name: str
    level: SkillLevel
    years: float
    provenance: Provenance


class ProfileFactsRead(StrictModel):
    """The facts of one revision as returned to clients."""

    schema_version: int
    headline: str
    base_location: BaseLocation
    years_experience: int
    languages: list[LanguageSkill]
    skills: list[SkillRead]
    experience: list[Experience]
    education: list[Education]
    certifications: list[Certification]
    # Revisions saved before ADR-057 have none; the stored facts always default to an empty list.
    directions: list[CareerDirection] = Field(default_factory=list)


class ProfileRevisionSummary(StrictModel):
    """One line of the history."""

    profile_revision_id: int
    revision_number: int
    created_at: datetime
    change_summary: str | None


class ProfileRevisionRead(ProfileRevisionSummary):
    """A revision with its facts and privacy settings."""

    facts: ProfileFactsRead
    privacy: ProfilePrivacy


class ProfileRead(StrictModel):
    """A profile with its current revision (``null`` for a blank profile)."""

    career_profile_id: int
    title: str
    visibility: Visibility
    version: int
    current_revision: ProfileRevisionRead | None


class ProfileList(StrictModel):
    """All of the owner's profiles."""

    items: list[ProfileRead]


class ProfileSaveResponse(StrictModel):
    """Result of a save or restore; ``created`` is false when nothing changed."""

    created: bool
    profile: ProfileRead


class ProfileRevisionList(StrictModel):
    """A profile's history, newest first."""

    items: list[ProfileRevisionSummary]
