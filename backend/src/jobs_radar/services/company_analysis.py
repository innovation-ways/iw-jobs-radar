"""The deep company analysis (ADR-054): public pages of the company's own website, local model.

The owner asks for it per company. The pages of the confirmed website are read (same domain only),
their text goes to the *local* model and never to a remote provider (ADR-046). It uses the larger
model chosen for career directions and job summaries (the job model if none is chosen), because the
small one only copied sentences. The model returns an overview, the kind of company, the remote
policy and short statements in its own words, each backed by a quote copied from a page. A statement
whose quote is not found on the page it names, or that merely repeats its quote, is dropped, like
job extraction (ADR-044). The result is one fact ``ai_dossier`` with origin ``ai_inference``; a
newer analysis supersedes the older one.
"""

import json
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.enrichment.website import WebPage, WebsiteUnreadableError
from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderError
from jobs_radar.core.errors import DependencyUnavailableError, InputValidationError, NotFoundError
from jobs_radar.db.models import Company, CompanyFact
from jobs_radar.domain.enums import FactOrigin
from jobs_radar.domain.text_match import quote_occurs
from jobs_radar.services.ai_settings import AiSettingsService

FACT_KEY = "ai_dossier"
TOPICS = (
    "offering",
    "customers",
    "locations",
    "size_and_stage",
    "financials",
    "technology",
    "remote_policy",
    "culture",
    "risks",
    "other",
)
COMPANY_TYPES = (
    "product",
    "consulting_outsourcing",
    "staffing_recruitment",
    "agency",
    "marketplace_platform",
    "other",
    "unknown",
)
REMOTE_POLICIES = ("remote", "hybrid", "on_site", "not_stated")
# A local model has a small context: the pages share this budget, the statements are bounded too.
PROMPT_TEXT_LIMIT = 24_000
MAX_STATEMENTS = 20
_OVERVIEW_LIMIT = 700
MAX_QUESTIONS = 5
_STATEMENT_LIMIT = 300
SYSTEM_PROMPT = "\n".join(
    [
        "You explain a company to a job seeker who wants to know what it is before applying. "
        "Use ONLY the web pages below; never add facts, numbers, names or opinions that are not "
        "on them. Write in English, in your own words, plainly.",
        '"overview": two or three sentences saying what the company does, for whom, and how it '
        "makes money (for example: sells a product, sells consulting or outsourced teams, places "
        "staff). Mention where it operates only if the pages say so.",
        f'"company_type": one of {", ".join(COMPANY_TYPES)}. Use "unknown" if the pages do not '
        "make it clear.",
        f'"remote_policy": one of {", ".join(REMOTE_POLICIES)}; "not_stated" unless the pages '
        "say how people work.",
        f'"statements": facts that are on the pages, each with a "topic" ({", ".join(TOPICS)}), '
        'a "text" in your own words (never a copy of the quote), a "quote" copied verbatim from '
        'the page named in "page_url", and that "page_url". A statement without a verbatim quote '
        "is discarded. Prefer concrete facts: services or products, customers or sectors, "
        "countries and cities, number of employees, clients or years, funding or revenue, "
        "technologies, work model. Do not make several statements from the same sentence.",
        'Never write that something is missing or not mentioned in a statement: list it in "open_'
        'questions" (at most five, the ones that matter most to a job seeker: size, profit or '
        "funding, where it operates, remote work).",
        'Answer with a JSON object {"overview", "company_type", "remote_policy", "statements": '
        '[{"topic", "text", "quote", "page_url"}], "open_questions": [""]}.',
    ]
)
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "company_type": {"type": "string", "enum": list(COMPANY_TYPES)},
        "remote_policy": {"type": "string", "enum": list(REMOTE_POLICIES)},
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
    "required": ["overview", "company_type", "remote_policy", "statements"],
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
        target = await self._ai.direction_target(owner_id)
        if target is None:
            msg = "Choose a local model for job analysis in AI & privacy to analyse companies."
            raise InputValidationError(msg)
        connection, provider = target

        try:
            pages = await self._reader.read(company.homepage_url)
        except WebsiteUnreadableError as error:
            raise self._unreadable(error) from error
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
            source_name=f"{connection.provider_type}:{provider.model}",
            source_url=company.homepage_url,
            retrieved_at=now,
            licence=None,
        )
        self._session.add(fact)
        await self._session.flush()
        await self._session.refresh(fact)
        return fact

    @staticmethod
    def _unreadable(error: WebsiteUnreadableError) -> DependencyUnavailableError:
        """Explain why the site was not read, so the owner knows whether to try again."""
        if error.reason == "refused":
            message = (
                f"The company website refused automated access (HTTP {error.status}). "
                "It is not read around; try a different address or skip this company."
            )
        elif error.reason == "too_large":
            message = "The company website's home page is too large to read."
        elif error.reason == "robots":
            message = "The company website asks robots not to read its pages (robots.txt)."
        else:
            status = f" (HTTP {error.status})" if error.status else ""
            message = f"The company website could not be reached{status}. Try again later."
        return DependencyUnavailableError(
            message, details={"error_class": f"site_{error.reason}", "status": error.status}
        )

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
        overview = data.get("overview")
        if not isinstance(overview, str) or not overview.strip():
            raise _invalid()
        overview = " ".join(overview.split())
        if len(overview) > _OVERVIEW_LIMIT:
            overview = overview[: _OVERVIEW_LIMIT - 1].rstrip() + "…"
        company_type = data.get("company_type")
        remote_policy = data.get("remote_policy")
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
                # A statement that only repeats its quote tells the reader nothing new.
                or " ".join(text.lower().split()) == " ".join(quote.lower().split())
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
            "overview": overview,
            "company_type": company_type if company_type in COMPANY_TYPES else "unknown",
            "remote_policy": remote_policy if remote_policy in REMOTE_POLICIES else "not_stated",
            "statements": kept,
            "open_questions": cleaned,
            "pages": [page.url for page in pages],
            "dropped": dropped,
        }
