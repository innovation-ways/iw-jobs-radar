"""API models for the job briefing (ADR-059)."""

from typing import Literal

from jobs_radar.schemas.common import StrictModel


class TechnologyRead(StrictModel):
    """One technology or system the posting asks for."""

    name: str
    importance: Literal["must", "nice"]


class JobBriefRead(StrictModel):
    """What is shown above the full description: the AI summary, the stack and the key facts."""

    summary: str | None
    summary_model: str | None
    technologies: list[TechnologyRead]
    facts: list[str]


class SummaryResponse(StrictModel):
    """A summary written (or already stored) for one job."""

    summary: str
    created: bool
