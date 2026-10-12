"""The AI company summary (T7.4): a short text, always labelled "AI inference".

Only public data goes to the model: the company's current non-AI facts, the overview of its website
analysis (when there is one) and the titles of its recent offers. It uses the *local* model chosen
for career directions and job summaries (the job model if none), never a remote provider
(ADR-046). The summary is stored as a fact with origin ``ai_inference`` and the model as its
source; a newer one supersedes the older. The model is told to use only the facts it is given.
"""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderError
from jobs_radar.core.errors import DependencyUnavailableError, InputValidationError, NotFoundError
from jobs_radar.db.models import Company, CompanyFact, JobOpportunity, JobPosting
from jobs_radar.domain.enums import FactOrigin
from jobs_radar.services.ai_settings import AiSettingsService

SUMMARY_LIMIT = 700
_TITLES = 15
SYSTEM_PROMPT = "\n".join(
    [
        "You write a neutral two or three sentence summary of a company for a job seeker.",
        "Use only the facts below. Never add facts, numbers, products or opinions that are not "
        "listed. If little is known, say little.",
        'Answer with a JSON object {"summary": "<text>"} and nothing else.',
    ]
)
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}


class CompanySummaryService:
    """Generates the summary. The caller owns the transaction."""

    def __init__(self, session: AsyncSession, ai: AiSettingsService) -> None:
        self._session = session
        self._ai = ai

    async def generate(self, owner_id: int, company_id: int) -> CompanyFact:
        """Write and store the summary.

        Raises:
            NotFoundError: unknown company.
            InputValidationError: no local model is chosen for job analysis.
            DependencyUnavailableError: the model failed or gave an unusable answer.
        """
        company = await self._session.get(Company, company_id)
        if company is None:
            msg = f"Company {company_id} does not exist."
            raise NotFoundError(msg)
        target = await self._ai.direction_target(owner_id)
        if target is None:
            msg = "Choose a local model for job analysis in AI & privacy to write summaries."
            raise InputValidationError(msg)
        connection, provider = target

        facts = (
            await self._session.execute(
                select(CompanyFact).where(
                    CompanyFact.company_id == company_id,
                    CompanyFact.superseded_at.is_(None),
                    CompanyFact.origin != FactOrigin.AI_INFERENCE.value,
                )
            )
        ).scalars()
        analysis = (
            await self._session.execute(
                select(CompanyFact.value_json).where(
                    CompanyFact.company_id == company_id,
                    CompanyFact.fact_key == "ai_dossier",
                    CompanyFact.superseded_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        titles = (
            await self._session.execute(
                select(JobPosting.title)
                .join(
                    JobOpportunity,
                    JobOpportunity.primary_job_posting_id == JobPosting.job_posting_id,
                )
                .where(JobOpportunity.company_id == company_id)
                .order_by(JobOpportunity.first_seen_at.desc())
                .limit(_TITLES)
            )
        ).scalars()
        lines = [f"Company: {company.canonical_name}"]
        lines += [f"{f.fact_key}: {json.dumps(f.value_json, ensure_ascii=False)}" for f in facts]
        # The website analysis is the best description there is; its overview leads the input.
        if isinstance(analysis, dict) and isinstance(analysis.get("overview"), str):
            lines.append(f"Website overview: {analysis['overview']}")
        title_list = list(titles)
        if title_list:
            lines.append("Recent job titles: " + "; ".join(title_list))
        try:
            output = await provider.extract(
                ExtractionRequest(system=SYSTEM_PROMPT, user="\n".join(lines), json_schema=_SCHEMA)
            )
        except ProviderError as error:
            raise DependencyUnavailableError(
                error.message, details={"error_class": error.error_class.value}
            ) from error
        text = self._text(output.content)

        now = datetime.now(UTC)
        previous = (
            await self._session.execute(
                select(CompanyFact).where(
                    CompanyFact.company_id == company_id,
                    CompanyFact.fact_key == "ai_summary",
                    CompanyFact.superseded_at.is_(None),
                )
            )
        ).scalars()
        for row in previous:
            row.superseded_at = now
        fact = CompanyFact(
            company_id=company_id,
            fact_key="ai_summary",
            value_json=text,
            origin=FactOrigin.AI_INFERENCE.value,
            source_name=f"{connection.provider_type}:{provider.model}",
            source_url=None,
            retrieved_at=now,
            licence=None,
        )
        self._session.add(fact)
        await self._session.flush()
        await self._session.refresh(fact)
        return fact

    @staticmethod
    def _text(answer: str) -> str:
        try:
            text = json.loads(answer)["summary"]
        except (ValueError, KeyError, TypeError) as error:
            raise DependencyUnavailableError(
                "The model returned an unusable summary.",
                details={"error_class": "invalid_response"},
            ) from error
        if not isinstance(text, str) or not text.strip():
            raise DependencyUnavailableError(
                "The model returned an unusable summary.",
                details={"error_class": "invalid_response"},
            )
        text = " ".join(text.split())
        return text if len(text) <= SUMMARY_LIMIT else text[: SUMMARY_LIMIT - 1].rstrip() + "…"
