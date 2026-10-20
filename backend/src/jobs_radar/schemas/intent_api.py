"""API contracts for search intents and the taxonomy (document 07, section 4)."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import Field, StringConstraints

from jobs_radar.schemas.common import StrictModel
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.profile import ProfilePrivacy
from jobs_radar.schemas.profile_api import ProfileFactsRead


class IntentCreate(IntentDefinition):
    """Create an intent with revision 1."""

    enabled: bool = True


class IntentSave(IntentDefinition):
    """Save the intent as its next revision."""

    expected_current_revision: int = Field(ge=1)
    change_summary: Annotated[str, StringConstraints(max_length=300)] | None = None


class VersionRequest(StrictModel):
    """Enable or disable using the row version the client saw."""

    expected_version: int = Field(ge=1)


class IntentRevisionRead(StrictModel):
    """One immutable intent revision."""

    intent_revision_id: int
    revision_number: int
    created_at: datetime
    change_summary: str | None
    definition: IntentDefinition


class IntentRead(StrictModel):
    """An intent with its current revision."""

    search_intent_id: int
    career_profile_id: int
    title: str
    enabled: bool
    version: int
    current_revision: IntentRevisionRead | None


class IntentList(StrictModel):
    """A profile's intents."""

    items: list[IntentRead]


class IntentSaveResponse(StrictModel):
    """Result of a save or restore; ``created`` is false when nothing changed."""

    created: bool
    intent: IntentRead


class IntentRevisionList(StrictModel):
    """An intent's history, newest first."""

    items: list[IntentRevisionRead]


class TaxonomyTermRead(StrictModel):
    """One term of a controlled vocabulary."""

    term_key: str
    label: str


class TaxonomyGroup(StrictModel):
    """The current terms of one vocabulary."""

    kind: str
    terms: list[TaxonomyTermRead]


class TaxonomyReplacement(StrictModel):
    """A term that was merged into another (ADR-080): saved intents may still use the old key."""

    kind: str
    from_key: str
    to_key: str


class TaxonomyRead(StrictModel):
    """All vocabularies."""

    groups: list[TaxonomyGroup]
    replacements: list[TaxonomyReplacement] = Field(default_factory=list)


class ExportedIntent(StrictModel):
    """An intent in the portable export."""

    title: str
    enabled: bool
    definition: IntentDefinition


class ExportedProfile(StrictModel):
    """The profile part of the portable export (``facts`` is null for a blank profile)."""

    title: str
    facts: ProfileFactsRead | None
    privacy: ProfilePrivacy | None


class ProfileExport(StrictModel):
    """Portable export of a profile and its intents; contains no secrets (document 07)."""

    schema_version: int = 1
    exported_at: datetime
    profile: ExportedProfile
    intents: list[ExportedIntent]
    # History and imports (UC-08): every revision, document metadata, proposals, inbox decisions.
    revisions: list[dict[str, Any]] = Field(default_factory=list)
    intent_revisions: list[dict[str, Any]] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)
    proposals: list[dict[str, Any]] = Field(default_factory=list)
    inbox: list[dict[str, Any]] = Field(default_factory=list)
