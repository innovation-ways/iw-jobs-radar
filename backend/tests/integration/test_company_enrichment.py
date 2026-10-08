"""Company enrichment: domain-match rule, unmatched candidates, sourced facts, refresh (T7.2)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import make_company, make_posting, make_source

from jobs_radar.adapters.enrichment.base import EnrichmentError, EntityCandidate, FactValue
from jobs_radar.adapters.enrichment.github import GitHubOrg
from jobs_radar.adapters.enrichment.gleif import LegalEntity
from jobs_radar.adapters.enrichment.wikipedia import WikipediaSummary
from jobs_radar.core.errors import ConflictError, NotFoundError
from jobs_radar.db.models import Company, CompanyEnrichmentCandidate, CompanyFact
from jobs_radar.services.enrichment import EnrichmentAdapters, EnrichmentService

pytestmark = pytest.mark.integration

NOW = datetime(2031, 5, 1, 9, 0, tzinfo=UTC)


def wd(value: object, key: str = "homepage") -> FactValue:
    return FactValue(value, "wikidata", "https://www.wikidata.org/wiki/Q1", "CC0-1.0")


def candidate(
    qid: str = "Q1", website: str | None = "https://www.northwind.example/", **extra: object
) -> EntityCandidate:
    facts = {
        "industry": wd("software industry"),
        "employee_count": wd(4000),
        "founded_year": wd(2013),
    }
    if website:
        facts["homepage"] = wd(website)
    return EntityCandidate(
        source_name="wikidata",
        external_id=qid,
        label="Northwind Labs",
        description="software company",
        website=website,
        facts=facts,
        wikipedia_title="Northwind Labs",
        github_login="northwind-labs",
        **extra,  # type: ignore[arg-type]
    )


class FakeWikidata:
    def __init__(self, found: list[EntityCandidate], error: EnrichmentError | None = None) -> None:
        self.found, self.error, self.calls = found, error, 0

    async def find(self, name: str) -> list[EntityCandidate]:
        self.calls += 1
        if self.error:
            raise self.error
        return self.found


class FakeWikipedia:
    def __init__(
        self, summary: WikipediaSummary | None = None, error: EnrichmentError | None = None
    ) -> None:
        self.summary_value, self.error = summary, error

    async def summary(self, title: str) -> WikipediaSummary | None:
        if self.error:
            raise self.error
        return self.summary_value


class FakeGleif:
    def __init__(self, entity: LegalEntity | None = None) -> None:
        self.entity = entity

    async def legal_entity(self, name: str) -> LegalEntity | None:
        return self.entity


class FakeGitHub:
    def __init__(self, org: GitHubOrg | None = None) -> None:
        self.org, self.logins = org, []

    async def organisation(self, login: str) -> GitHubOrg | None:
        self.logins.append(login)
        return self.org


SUMMARY = WikipediaSummary(
    "Northwind Labs",
    "Northwind Labs is a software company.",
    "https://en.wikipedia.org/wiki/Northwind_Labs",
)
LEGAL = LegalEntity(
    "LEI1", "NORTHWIND LABS, INC.", "US", "ACTIVE", "https://search.gleif.org/#/record/LEI1"
)
ORG = GitHubOrg(
    "northwind-labs",
    "https://northwind.example",
    "We build",
    12,
    ["Python", "Go"],
    "https://github.com/northwind-labs",
)


def service(
    session: AsyncSession,
    found: list[EntityCandidate],
    *,
    summary=SUMMARY,
    legal=LEGAL,
    org=ORG,
    clock=lambda: NOW,
    wikidata=None,
):  # type: ignore[no-untyped-def]
    adapters = EnrichmentAdapters(
        wikidata=wikidata or FakeWikidata(found),
        wikipedia=FakeWikipedia(summary),
        gleif=FakeGleif(legal),
        github=FakeGitHub(org),
    )
    return EnrichmentService(session, adapters, clock=clock), adapters


async def company_with_domain(
    session: AsyncSession, domain: str | None = "northwind.example"
) -> int:
    company = await make_company(session, "Northwind Labs")
    if domain:
        company.careers_url = f"https://careers.{domain}/jobs"
    await session.flush()
    return company.company_id


async def facts_of(session: AsyncSession, company_id: int) -> dict[str, CompanyFact]:
    rows = (
        await session.execute(
            select(CompanyFact).where(
                CompanyFact.company_id == company_id, CompanyFact.superseded_at.is_(None)
            )
        )
    ).scalars()
    return {f.fact_key: f for f in rows}


async def test_a_candidate_whose_website_domain_matches_is_accepted_with_sourced_facts(
    db_session: AsyncSession,
) -> None:
    company_id = await company_with_domain(db_session)
    svc, _ = service(db_session, [candidate()])
    result = await svc.enrich(1, company_id)
    assert (
        result.accepted is not None and result.accepted.external_id == "Q1" and result.pending == []
    )
    facts = await facts_of(db_session, company_id)
    assert facts["industry"].value_json == "software industry"
    assert (facts["industry"].origin, facts["industry"].source_name, facts["industry"].licence) == (
        "public_dataset",
        "wikidata",
        "CC0-1.0",
    )
    assert (
        facts["industry"].source_url == "https://www.wikidata.org/wiki/Q1"
        and facts["industry"].retrieved_at == NOW
    )
    assert facts["description"].licence == "CC-BY-SA-4.0" and facts[
        "description"
    ].source_url.startswith("https://en.wikipedia.org")
    assert (
        facts["legal_entity"].value_json["lei"] == "LEI1"
        and facts["legal_entity"].licence == "CC0-1.0"
    )
    assert facts["technologies"].value_json == ["Python", "Go"]
    company = await db_session.get(Company, company_id)
    assert company.homepage_url == "https://www.northwind.example/" and company.enriched_at == NOW  # type: ignore[union-attr]


async def test_a_different_domain_stays_unmatched_until_the_owner_confirms(
    db_session: AsyncSession,
) -> None:
    company_id = await company_with_domain(db_session, "other.example")
    svc, adapters = service(db_session, [candidate()])
    result = await svc.enrich(1, company_id)
    assert result.accepted is None and [c.external_id for c in result.pending] == ["Q1"]
    assert await facts_of(db_session, company_id) == {}  # nothing is stored as a fact yet
    assert (
        adapters.github.logins == []
    )  # and no secondary source is queried for an unconfirmed entity

    confirmed = await svc.confirm(1, company_id, result.pending[0].company_enrichment_candidate_id)
    assert confirmed.status == "accepted" and confirmed.decided_by == "user"
    assert "industry" in await facts_of(db_session, company_id)


async def test_a_company_with_no_known_domain_is_never_auto_matched(
    db_session: AsyncSession,
) -> None:
    company_id = await company_with_domain(db_session, None)
    svc, _ = service(db_session, [candidate()])
    assert (await svc.enrich(1, company_id)).accepted is None


async def test_job_board_hosts_do_not_count_as_the_company_domain(db_session: AsyncSession) -> None:
    company = await make_company(db_session, "Northwind Labs")
    source = await make_source(db_session, company)
    posting, _ = await make_posting(db_session, source)
    posting.source_url = "https://boards.greenhouse.io/northwind-labs/jobs/1"
    await db_session.flush()
    svc, _ = service(db_session, [candidate(website="https://boards.greenhouse.io")])
    assert (await svc.enrich(1, company.company_id)).accepted is None


async def test_the_company_domain_can_come_from_its_postings(db_session: AsyncSession) -> None:
    company = await make_company(db_session, "Northwind Labs")
    source = await make_source(db_session, company)
    posting, _ = await make_posting(db_session, source)
    posting.source_url = "https://www.northwind.example/careers/42"
    await db_session.flush()
    svc, _ = service(db_session, [candidate()])
    assert (await svc.enrich(1, company.company_id)).accepted is not None


async def test_a_rejected_candidate_is_not_proposed_again(db_session: AsyncSession) -> None:
    company_id = await company_with_domain(db_session, "other.example")
    svc, _ = service(db_session, [candidate()])
    first = await svc.enrich(1, company_id)
    await svc.reject(1, company_id, first.pending[0].company_enrichment_candidate_id)
    again = await svc.enrich(1, company_id)
    assert again.pending == []
    rows = (
        (
            await db_session.execute(
                select(CompanyEnrichmentCandidate).where(
                    CompanyEnrichmentCandidate.company_id == company_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert [r.status for r in rows] == ["rejected"]


async def test_deciding_twice_or_for_another_company_is_refused(db_session: AsyncSession) -> None:
    company_id = await company_with_domain(db_session, "other.example")
    other = await company_with_domain(db_session, "x.example")
    svc, _ = service(db_session, [candidate()])
    pending = (await svc.enrich(1, company_id)).pending[0]
    with pytest.raises(NotFoundError):
        await svc.confirm(1, other, pending.company_enrichment_candidate_id)
    await svc.confirm(1, company_id, pending.company_enrichment_candidate_id)
    with pytest.raises(ConflictError):
        await svc.reject(1, company_id, pending.company_enrichment_candidate_id)
    with pytest.raises(NotFoundError):
        await svc.enrich(1, 999_999)


async def test_github_is_used_only_when_its_website_matches_the_entity(
    db_session: AsyncSession,
) -> None:
    company_id = await company_with_domain(db_session)
    wrong_org = GitHubOrg(
        "northwind-labs",
        "https://someone-else.example",
        None,
        3,
        ["Rust"],
        "https://github.com/northwind-labs",
    )
    svc, _ = service(db_session, [candidate()], org=wrong_org)
    await svc.enrich(1, company_id)
    assert "technologies" not in await facts_of(db_session, company_id)


async def test_a_failing_secondary_source_does_not_lose_the_rest(db_session: AsyncSession) -> None:
    company_id = await company_with_domain(db_session)
    adapters = EnrichmentAdapters(
        wikidata=FakeWikidata([candidate()]),
        wikipedia=FakeWikipedia(error=EnrichmentError("unavailable", "down")),
        gleif=FakeGleif(LEGAL),
        github=FakeGitHub(ORG),
    )
    result = await EnrichmentService(db_session, adapters, clock=lambda: NOW).enrich(1, company_id)
    facts = await facts_of(db_session, company_id)
    assert "industry" in facts and "description" not in facts and "legal_entity" in facts
    assert any("wikipedia" in w for w in result.warnings)


async def test_a_failing_primary_source_is_reported_and_changes_nothing(
    db_session: AsyncSession,
) -> None:
    from jobs_radar.core.errors import DependencyUnavailableError

    company_id = await company_with_domain(db_session)
    svc, _ = service(
        db_session, [], wikidata=FakeWikidata([], error=EnrichmentError("rate_limited", "slow"))
    )
    with pytest.raises(DependencyUnavailableError) as caught:
        await svc.enrich(1, company_id)
    assert caught.value.details["error_class"] == "rate_limited"
    assert await facts_of(db_session, company_id) == {}


async def test_a_changed_fact_supersedes_the_old_one_and_an_equal_one_is_kept(
    db_session: AsyncSession,
) -> None:
    company_id = await company_with_domain(db_session)
    svc, _ = service(db_session, [candidate()])
    await svc.enrich(1, company_id)
    later = NOW + timedelta(days=40)
    changed = candidate()
    changed.facts["employee_count"] = wd(5000)
    svc2, _ = service(db_session, [changed], clock=lambda: later)
    await svc2.enrich(1, company_id)
    rows = (
        (
            await db_session.execute(
                select(CompanyFact)
                .where(
                    CompanyFact.company_id == company_id, CompanyFact.fact_key == "employee_count"
                )
                .order_by(CompanyFact.company_fact_id)
            )
        )
        .scalars()
        .all()
    )
    assert [(r.value_json, r.superseded_at) for r in rows] == [(4000, later), (5000, None)]
    industry = (
        (
            await db_session.execute(
                select(CompanyFact).where(
                    CompanyFact.company_id == company_id, CompanyFact.fact_key == "industry"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(industry) == 1  # unchanged facts are not duplicated


async def test_a_company_is_stale_after_thirty_days_or_when_never_enriched(
    db_session: AsyncSession,
) -> None:
    company_id = await company_with_domain(db_session)
    svc, _ = service(db_session, [candidate()])
    assert await svc.is_stale(company_id) is True
    await svc.enrich(1, company_id)
    assert await svc.is_stale(company_id) is False
    later, _ = service(db_session, [], clock=lambda: NOW + timedelta(days=31))
    assert await later.is_stale(company_id) is True
