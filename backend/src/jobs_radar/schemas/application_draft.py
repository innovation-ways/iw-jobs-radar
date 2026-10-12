"""The pre-application draft: strengths, positioning, gaps and a cover-letter base (ADR-064)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from jobs_radar.schemas.common import StrictModel

LetterLanguage = Literal["pt", "en"]
MIN_STRENGTHS = 3
MAX_STRENGTHS = 6
MAX_GAPS = 4
MIN_LETTER_WORDS = 150
MAX_LETTER_WORDS = 450
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=400)]


class Strength(StrictModel):
    """One point to stress and the profile fact it rests on."""

    point: Line
    evidence: Line


class ApplicationContent(StrictModel):
    """What the model wrote for one job; stored in ``application_draft.draft_json``."""

    schema_version: Literal[1] = 1
    strengths: list[Strength] = Field(min_length=MIN_STRENGTHS, max_length=MAX_STRENGTHS)
    positioning: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=20, max_length=900)
    ]
    gaps: list[Line] = Field(default_factory=list, max_length=MAX_GAPS)
    cover_letter: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
    letter_language: LetterLanguage


class ApplicationDraftRead(StrictModel):
    """A stored draft as returned to clients."""

    application_draft_id: int
    created_at: datetime
    model: str
    prompt_version: str
    draft: ApplicationContent


class ApplicationDraftList(StrictModel):
    """The drafts of one job, newest first."""

    items: list[ApplicationDraftRead]
