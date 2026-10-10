"""The deep company analysis (ADR-054): public pages of the company's own website, local model.

The owner asks for it per company. The pages of the confirmed website are read (same domain only),
their text goes to the *local* model chosen for job analysis (ADR-046) and never to a remote
provider, and the model returns short statements, each with a quote copied from a page. A statement
whose quote is not found on the page it names is dropped, like job extraction (ADR-044). The result
is one fact ``ai_dossier`` with origin ``ai_inference``; a newer analysis supersedes the older one.
"""

import json
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.enrichment.website import WebPage
from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderError
from jobs_radar.core.errors import DependencyUnavailableError, InputValidationError, NotFoundError
from jobs_radar.db.models import Company, CompanyFact
from jobs_radar.domain.enums import FactOrigin
from jobs_radar.domain.text_match import quote_occurs
from jobs_radar.services.ai_settings import AiSettingsService

FACT_KEY = "ai_dossier"
TOPICS = (
    "product",
    "business_model",
    "size_and_stage",
    "technology",
    "engineering_culture",
    "remote_policy",
    "portugal_presence",
    "risks",
    "other",
)
# A local model has a small context: the pages share this budget, the statements are bounded too.
PROMPT_TEXT_LIMIT = 14_000
MAX_STATEMENTS = 24
MAX_QUESTIONS = 5
_STATEMENT_LIMIT = 300
SYSTEM_PROMPT = "\n".join(
    [
        "You describe a company for a job seeker using ONLY the web pages below.",
        "Never add facts, numbers, names or opinions that are not on the pages.",
        f"Give statements, each with one of these topics: {', '.join(TOPICS)}.",
        'Every statement needs a "quote": an exact quote copied verbatim from the page named in '
        '"page_url". A statement without a verbatim quote is discarded.',
        "Cover remote or hybrid policy and any presence in Portugal only when the pages say it. "
        "Never write a statement that something is missing or not mentioned: put that in "
        '"open_questions" instead.',
        'List in "open_questions" what the pages do not answer. Answer with a JSON object '
        '{"statements": [{"topic", "text", "quote", "page_url"}], "open_questions": [""]}.',
    ]
)
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "statements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "enum": list(TOPICS)},
                    "text": {"type": "string"},
                    "quote": {"type": "string"},
                    "page_url": {"type": "string"},
                },
                "required": ["topic", "text", "quote", "page_url"],
            },
        },
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["statements"],
}


class SiteReader(Protocol):
    """Reads the public pages of a website."""

    async def read(self, home_url: str) -> list[WebPage]:
        """Return the pages' text (an unreadable site gives an empty list)."""
        ...


def _invalid() -> DependencyUnavailableError:
    return DependencyUnavailableError(
        "The model returned no statement that the pages support.",
        details={"error_class": "invalid_response"},
    )


class CompanyAnalysisService:
    """Analyses a company's website. The caller owns the transaction."""

    def __init__(self, session: AsyncSession, ai: AiSettingsService, *, reader: SiteReader) -> None:
        self._session = session
        self._ai = ai
        self._reader = reader

    async def analyse(self, owner_id: int, company_id: int) -> CompanyFact:
        """Read the website, ask the local model and store the verified dossier.

        Raises:
            NotFoundError: unknown company.
            InputValidationError: no website is confirmed, or no local model is chosen.
            DependencyUnavailableError: the site could not be read, the model failed, or none of
                its statements is supported by the pages.
        """
        company = await self._session.get(Company, company_id)
        if company is None:
            msg = f"Company {company_id} does not exist."
            raise NotFoundError(msg)
        if not company.homepage_url:
            msg = "Add or confirm the company's website before analysing it."
            raise InputValidationError(msg)
        target = await self._ai.jobs_target(owner_id)
        if target is None:
            msg = "Choose a local model for job analysis in AI & privacy to analyse companies."
            raise InputValidationError(msg)
        connection, provider = target

        pages = await self._reader.read(company.homepage_url)
        if not pages:
            raise DependencyUnavailableError(
                "The company website could not be read.",
                details={"error_class": "site_unreadable"},
            )
        budget = PROMPT_TEXT_LIMIT // len(pages)
        sections = [f"PAGE {page.url}\n{page.text[:budget]}" for page in pages]
        user = f"Company: {company.canonical_name}\n\n" + "\n\n".join(sections)
        try:
            output = await provider.extract(
                ExtractionRequest(system=SYSTEM_PROMPT, user=user, json_schema=_SCHEMA)
            )
        except ProviderError as error:
            raise DependencyUnavailableError(
                error.message, details={"error_class": error.error_class.value}
            ) from error

        value = self._verified(output.content, pages)
        now = datetime.now(UTC)
        previous = (
            await self._session.execute(
                select(CompanyFact).where(
                    CompanyFact.company_id == company_id,
                    CompanyFact.fact_key == FACT_KEY,
                    CompanyFact.superseded_at.is_(None),
                )
            )
        ).scalars()
        for row in previous:
            row.superseded_at = now
        fact = CompanyFact(
            company_id=company_id,
            fact_key=FACT_KEY,
            value_json=value,
            origin=FactOrigin.AI_INFERENCE.value,
            source_name=f"{connection.provider_type}:{connection.model_id}",
            source_url=company.homepage_url,
            retrieved_at=now,
            licence=None,
        )
        self._session.add(fact)
        await self._session.flush()
        await self._session.refresh(fact)
        return fact

    @staticmethod
    def _verified(answer: str, pages: list[WebPage]) -> dict[str, Any]:
        """Keep the statements whose quote occurs on the page they name; count the others."""
        try:
            data = json.loads(answer)
            raw = data["statements"]
        except (ValueError, KeyError, TypeError) as error:
            raise _invalid() from error
        if not isinstance(raw, list):
            raise _invalid()
        by_url = {page.url: page.text for page in pages}
        kept: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        dropped = 0
        for item in raw:
            values = (
                [item.get(k) for k in ("topic", "text", "quote", "page_url")]
                if isinstance(item, dict)
                else []
            )
            strings = [v for v in values if isinstance(v, str) and v.strip()]
            if len(strings) != 4:
                dropped += 1
                continue
            topic, text, quote, url = (" ".join(v.split()) for v in strings)
            key = (topic, text.lower())
            if (
                topic not in TOPICS
                or url not in by_url
                or not quote_occurs(quote, by_url[url])
                or key in seen
                or len(kept) >= MAX_STATEMENTS
            ):
                dropped += 1
                continue
            seen.add(key)
            kept.append(
                {"topic": topic, "text": text[:_STATEMENT_LIMIT], "quote": quote, "page_url": url}
            )
        if not kept:
            raise _invalid()
        questions = data.get("open_questions")
        cleaned = [
            " ".join(q.split())[:_STATEMENT_LIMIT]
            for q in (questions if isinstance(questions, list) else [])
            if isinstance(q, str) and q.strip()
        ][:MAX_QUESTIONS]
        return {
            "statements": kept,
            "open_questions": cleaned,
            "pages": [page.url for page in pages],
            "dropped": dropped,
        }
