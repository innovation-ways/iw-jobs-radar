"""Assembles the briefing of one job: the stored summary, the technologies and the key facts.

Everything here is read from rows that already exist, so opening a job never calls a model. The
summary is the newest successful one of the posting's latest snapshot (a changed posting shows no
summary until a new one is written); technologies and facts come from the latest successful
extraction (ADR-059).
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import JobExtraction
from jobs_radar.domain.job_brief import key_facts, technologies
from jobs_radar.repositories.evaluations import EvaluationRepository
from jobs_radar.repositories.summaries import SummaryRepository


@dataclass(frozen=True)
class JobBrief:
    """What the detail panel shows above the full description."""

    summary: str | None = None
    summary_model: str | None = None
    technologies: list[dict[str, str]] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)


class JobBriefService:
    """Reads the briefing of a posting."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._summaries = SummaryRepository(session)
        self._evaluations = EvaluationRepository(session)

    async def for_posting(self, job_posting_id: int) -> JobBrief:
        """Return the briefing of the posting; every part is empty when it is not available."""
        summary_text: str | None = None
        summary_model: str | None = None
        snapshot_id = await self._summaries.latest_snapshot_id(job_posting_id)
        if snapshot_id is not None:
            written = await self._summaries.latest_success(snapshot_id)
            if written is not None:
                summary_text, summary_model = written.summary_text, written.model
        output: dict[str, Any] = {}
        found = await self._evaluations.latest_extraction(job_posting_id)
        if found is not None:
            extraction = await self._session.get(JobExtraction, found[1])
            if extraction is not None:
                output = (extraction.attributes_json or {}).get("output") or {}
        return JobBrief(summary_text, summary_model, technologies(output), key_facts(output))
