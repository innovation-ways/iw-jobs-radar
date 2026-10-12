"""Company enrichment from free public datasets (T7.2, ADR-025, research R-00171).

Wikidata is queried by the company name. An entity is accepted automatically only when the
registered domain of its official website equals a domain already known for the company (its
careers or homepage address, or the address of one of its postings off a job board); every other
entity is stored as a *pending* candidate that the owner confirms or rejects, and a rejected one is
never proposed again. Once an entity is accepted, Wikipedia (description, with attribution), GLEIF
(legal entity) and GitHub (technologies, only if the organisation's website matches) add facts.
Each fact keeps source, address, retrieval time and licence; a changed fact supersedes the old one.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.enrichment.base import EnrichmentError, EntityCandidate, FactValue
from jobs_radar.adapters.enrichment.github import GitHubOrg
from jobs_radar.adapters.enrichment.gleif import LegalEntity
from jobs_radar.adapters.enrichment.wikipedia import WikipediaSummary
from jobs_radar.core.errors import ConflictError, DependencyUnavailableError, NotFoundError
from jobs_radar.db.models import Company, CompanyEnrichmentCandidate, CompanyFact, JobPosting
from jobs_radar.domain.domains import https_url, is_job_board_host, registered_domain
from jobs_radar.domain.enums import EnrichmentCandidateStatus, FactOrigin

Clock = Callable[[], datetime]
REFRESH_AFTER = timedelta(days=30)
MAX_PENDING = 3


class WikidataPort(Protocol):
    """Finds company entities by name."""

    async def find(self, name: str) -> list[EntityCandidate]:
        """Return entities that look like the company."""
        ...


class WikipediaPort(Protocol):
    """Reads an article summary."""

    async def summary(self, title: str) -> WikipediaSummary | None:
        """Return the summary or ``None``."""
        ...


class GleifPort(Protocol):
    """Finds a legal entity by name."""

    async def legal_entity(self, name: str) -> LegalEntity | None:
        """Return the one exact match or ``None``."""
        ...


class GitHubPort(Protocol):
    """Reads a GitHub organisation."""

    async def organisation(self, login: str) -> GitHubOrg | None:
        """Return the organisation or ``None``."""
        ...


@dataclass(frozen=True)
class EnrichmentAdapters:
    """The datasets enrichment can use (all optional except Wikidata)."""

    wikidata: WikidataPort
    wikipedia: WikipediaPort | None = None
    gleif: GleifPort | None = None
    github: GitHubPort | None = None


@dataclass
class EnrichmentResult:
    """What an enrichment run found."""

    accepted: CompanyEnrichmentCandidate | None
    pending: list[CompanyEnrichmentCandidate]
    warnings: list[str] = field(default_factory=list)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _payload(facts: dict[str, FactValue]) -> dict[str, Any]:
    return {
        key: {
            "value": fact.value,
            "source_name": fact.source_name,
            "source_url": fact.source_url,
            "licence": fact.licence,
        }
        for key, fact in facts.items()
    }


class EnrichmentService:
    """Enriches companies. The caller owns the transaction."""

    def __init__(
        self, session: AsyncSession, adapters: EnrichmentAdapters, *, clock: Clock = _utc_now
    ) -> None:
        self._session = session
        self._adapters = adapters
        self._clock = clock

    # --- helpers ---------------------------------------------------------------------------

    async def _company(self, company_id: int) -> Company:
        company = await self._session.get(Company, company_id)
        if company is None:
            msg = f"Company {company_id} does not exist."
            raise NotFoundError(msg)
        return company

    async def is_stale(self, company_id: int) -> bool:
        """Whether the company was never enriched or not within the last 30 days."""
        company = await self._company(company_id)
        return company.enriched_at is None or self._clock() - company.enriched_at > REFRESH_AFTER

    async def _known_domains(self, company: Company) -> set[str]:
        urls = [company.homepage_url, company.careers_url]
        rows = await self._session.execute(
            select(JobPosting.source_url)
            .where(JobPosting.company_id == company.company_id)
            .distinct()
            .limit(50)
        )
        urls.extend(rows.scalars())
        return {
            domain
            for url in urls
            if url and not is_job_board_host(url) and (domain := registered_domain(url))
        }

    async def _set_fact(
        self,
        company_id: int,
        key: str,
        value: Any,
        *,
        origin: FactOrigin,
        source_name: str,
        source_url: str | None,
        licence: str | None,
    ) -> None:
        now = self._clock()
        current = (
            (
                await self._session.execute(
                    select(CompanyFact).where(
                        CompanyFact.company_id == company_id,
                        CompanyFact.fact_key == key,
                        CompanyFact.superseded_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        if any(row.value_json == value for row in current):
            return
        for row in current:
            row.superseded_at = now
        self._session.add(
            CompanyFact(
                company_id=company_id,
                fact_key=key,
                value_json=value,
                origin=origin.value,
                source_name=source_name,
                source_url=source_url,
                retrieved_at=now,
                licence=licence,
            )
        )
        await self._session.flush()

    # --- enrichment ------------------------------------------------------------------------

    async def enrich(self, owner_id: int, company_id: int) -> EnrichmentResult:
        """Look the company up and apply what the domain rule accepts.

        Raises:
            NotFoundError: unknown company.
            DependencyUnavailableError: Wikidata could not be read.
        """
        del owner_id  # companies are shared reference data in V1
        company = await self._company(company_id)
        known = await self._known_domains(company)
        try:
            found = await self._adapters.wikidata.find(company.canonical_name)
        except EnrichmentError as error:
            raise DependencyUnavailableError(
                error.message, details={"error_class": error.error_class}
            ) from error

        existing = {
            c.external_id: c
            for c in (
                await self._session.execute(
                    select(CompanyEnrichmentCandidate).where(
                        CompanyEnrichmentCandidate.company_id == company_id,
                        CompanyEnrichmentCandidate.source_name == "wikidata",
                    )
                )
            ).scalars()
        }
        accepted: CompanyEnrichmentCandidate | None = next(
            (c for c in existing.values() if c.status == "accepted"), None
        )
        pending: list[CompanyEnrichmentCandidate] = []
        warnings: list[str] = []
        now = self._clock()
        for entity in found:
            row = existing.get(entity.external_id)
            matches = bool(entity.website) and registered_domain(entity.website or "") in known
            if row is None:
                if len(pending) >= MAX_PENDING and not matches:
                    continue
                row = CompanyEnrichmentCandidate(
                    company_id=company_id,
                    source_name="wikidata",
                    external_id=entity.external_id,
                    label=entity.label,
                    description=entity.description,
                    website=entity.website,
                    payload_json={
                        **_payload(entity.facts),
                        "_links": {
                            "wikipedia_title": entity.wikipedia_title,
                            "github_login": entity.github_login,
                        },
                    },
                )
                self._session.add(row)
                await self._session.flush()
            elif row.status == "accepted":
                # Re-reading an accepted entity refreshes its facts.
                row.payload_json = {
                    **_payload(entity.facts),
                    "_links": {
                        "wikipedia_title": entity.wikipedia_title,
                        "github_login": entity.github_login,
                    },
                }
            if row.status == "pending" and matches and accepted is None:
                row.status = EnrichmentCandidateStatus.ACCEPTED.value
                row.decided_by, row.decided_at = "domain_match", now
            if row.status == "accepted":
                accepted = accepted or row
            elif row.status == "pending":
                pending.append(row)
        await self._session.flush()
        if accepted is not None:
            warnings.extend(await self._apply(company, accepted))
        company.enriched_at = now
        await self._session.flush()
        return EnrichmentResult(accepted, pending, warnings)

    async def _apply(self, company: Company, candidate: CompanyEnrichmentCandidate) -> list[str]:
        """Write the accepted entity's facts and add the secondary sources; return warnings."""
        warnings: list[str] = []
        payload: dict[str, Any] = dict(candidate.payload_json or {})
        links = payload.pop("_links", {}) or {}
        for key, item in payload.items():
            await self._set_fact(
                company.company_id,
                key,
                item["value"],
                origin=FactOrigin.PUBLIC_DATASET,
                source_name=item["source_name"],
                source_url=item["source_url"],
                licence=item["licence"],
            )
        homepage = payload.get("homepage", {}).get("value")
        if isinstance(homepage, str):
            # The guarded HTTP client fetches https only; datasets often list plain http.
            company.homepage_url = https_url(homepage)

        adapters = self._adapters
        if adapters.wikipedia is not None and links.get("wikipedia_title"):
            try:
                summary = await adapters.wikipedia.summary(links["wikipedia_title"])
            except EnrichmentError:
                warnings.append("wikipedia: could not be read")
                summary = None
            if summary is not None:
                await self._set_fact(
                    company.company_id,
                    "description",
                    summary.text,
                    origin=FactOrigin.PUBLIC_DATASET,
                    source_name="wikipedia",
                    source_url=summary.url,
                    licence=summary.licence,
                )
        if adapters.gleif is not None:
            try:
                legal = await adapters.gleif.legal_entity(company.canonical_name)
            except EnrichmentError:
                warnings.append("gleif: could not be read")
                legal = None
            if legal is not None:
                await self._set_fact(
                    company.company_id,
                    "legal_entity",
                    {
                        "lei": legal.lei,
                        "name": legal.legal_name,
                        "country": legal.country,
                        "status": legal.status,
                    },
                    origin=FactOrigin.PUBLIC_DATASET,
                    source_name="gleif",
                    source_url=legal.url,
                    licence=legal.licence,
                )
        if adapters.github is not None and links.get("github_login"):
            try:
                org = await adapters.github.organisation(links["github_login"])
            except EnrichmentError:
                warnings.append("github: could not be read")
                org = None
            same_site = (
                org is not None
                and org.website is not None
                and isinstance(homepage, str)
                and registered_domain(org.website) == registered_domain(homepage)
            )
            if org is not None and same_site and org.languages:
                await self._set_fact(
                    company.company_id,
                    "technologies",
                    org.languages,
                    origin=FactOrigin.PUBLIC_DATASET,
                    source_name="github",
                    source_url=org.url,
                    licence=org.licence,
                )
        return warnings

    # --- the owner's decisions ---------------------------------------------------------------

    async def _candidate(self, company_id: int, candidate_id: int) -> CompanyEnrichmentCandidate:
        row = await self._session.get(CompanyEnrichmentCandidate, candidate_id)
        if row is None or row.company_id != company_id:
            msg = f"Candidate {candidate_id} does not exist for this company."
            raise NotFoundError(msg)
        if row.status != "pending":
            msg = "This candidate was already decided."
            raise ConflictError(msg)
        return row

    async def confirm(
        self, owner_id: int, company_id: int, candidate_id: int
    ) -> CompanyEnrichmentCandidate:
        """Record that the owner says this entity is the company, and store its facts."""
        del owner_id
        company = await self._company(company_id)
        row = await self._candidate(company_id, candidate_id)
        row.status = EnrichmentCandidateStatus.ACCEPTED.value
        row.decided_by, row.decided_at = "user", self._clock()
        await self._apply(company, row)
        await self._session.flush()
        return row

    async def reject(
        self, owner_id: int, company_id: int, candidate_id: int
    ) -> CompanyEnrichmentCandidate:
        """Record that the owner says this entity is not the company (never proposed again)."""
        del owner_id
        await self._company(company_id)
        row = await self._candidate(company_id, candidate_id)
        row.status = EnrichmentCandidateStatus.REJECTED.value
        row.decided_by, row.decided_at = "user", self._clock()
        await self._session.flush()
        return row
