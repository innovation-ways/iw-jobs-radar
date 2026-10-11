"""Company dossier: current facts with provenance, pending candidates, offers and hiring series (T7.3)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import (
    make_company,
    make_evaluation,
    make_extraction,
    make_intent,
    make_opportunity,
    make_posting,
    make_profile,
    make_source,
)

from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import CompanyEnrichmentCandidate, CompanyFact, JobInboxItem
from jobs_radar.domain.enums import Recommendation
from jobs_radar.services.companies import CompanyService

pytestmark = pytest.mark.integration

NOW = datetime(2032, 6, 16, 12, 0, tzinfo=UTC)  # a Wednesday; weeks start on Monday


async def test_the_dossier_lists_current_facts_with_their_sources(db_session: AsyncSession) -> None:
    company = await make_company(db_session, "Dossier Co")
    old = CompanyFact(
        company_id=company.company_id,
        fact_key="employee_count",
        value_json=100,
        origin="public_dataset",
        source_name="wikidata",
        source_url="https://www.wikidata.org/wiki/Q1",
        retrieved_at=NOW - timedelta(days=60),
        licence="CC0-1.0",
        superseded_at=NOW - timedelta(days=1),
    )
    new = CompanyFact(
        company_id=company.company_id,
        fact_key="employee_count",
        value_json=120,
        origin="public_dataset",
        source_name="wikidata",
        source_url="https://www.wikidata.org/wiki/Q1",
        retrieved_at=NOW - timedelta(days=1),
        licence="CC0-1.0",
    )
    ai = CompanyFact(
        company_id=company.company_id,
        fact_key="ai_summary",
        value_json="A software company.",
        origin="ai_inference",
        source_name="local-model",
        source_url=None,
        retrieved_at=NOW,
        licence=None,
    )
    db_session.add_all([old, new, ai])
    db_session.add(
        CompanyEnrichmentCandidate(
            company_id=company.company_id,
            source_name="wikidata",
            external_id="Q9",
            label="Dossier Company",
            description="company",
            website="https://dossier.example",
            payload_json={},
        )
    )
    await db_session.flush()
    dossier = await CompanyService(db_session, clock=lambda: NOW).dossier(
        1, company.company_id, search_intent_id=None
    )
    facts = {f.fact_key: f for f in dossier.facts}
    assert facts["employee_count"].value == 120 and facts["employee_count"].source_url.endswith(
        "Q1"
    )
    assert facts["ai_summary"].origin == "ai_inference"
    assert [c.external_id for c in dossier.candidates] == ["Q9"]
    assert dossier.stale is True  # never enriched


async def test_offers_and_the_weekly_hiring_series(db_session: AsyncSession) -> None:
    company = await make_company(db_session, "Hiring Co")
    source = await make_source(db_session, company)
    profile, profile_revision = await make_profile(db_session)
    intent, intent_revision = await make_intent(db_session, profile)
    ages = [(2, None), (9, 80), (10, None), (40, None)]  # days before NOW
    for age, fit in ages:
        posting, snapshot = await make_posting(
            db_session, source, title=f"Job {age}", first_seen_at=NOW - timedelta(days=age)
        )
        opportunity = await make_opportunity(db_session, posting)
        if age == 40:
            opportunity.closed_at = NOW - timedelta(days=20)
        if fit is not None:
            await make_evaluation(
                db_session,
                snapshot,
                await make_extraction(db_session, snapshot),
                profile_revision,
                intent_revision,
                fit_score=fit,
                recommendation=Recommendation.RECOMMENDED,
            )
    await db_session.flush()
    service = CompanyService(db_session, clock=lambda: NOW)
    recent = await service.dossier(1, company.company_id, search_intent_id=intent.search_intent_id)
    # Job 40 is older than the 30-day limit: left out unless asked for.
    assert [o.title for o in recent.offers] == ["Job 9", "Job 2", "Job 10"]  # best fit, then newest
    dossier = await service.dossier(
        1, company.company_id, search_intent_id=intent.search_intent_id, include_older=True
    )
    titles = [o.title for o in dossier.offers]
    assert titles == ["Job 9", "Job 2", "Job 10", "Job 40"]
    by_title = {o.title: o for o in dossier.offers}
    assert by_title["Job 9"].fit_score == 80 and by_title["Job 2"].fit_score is None
    assert by_title["Job 40"].closed is True and by_title["Job 2"].closed is False
    assert (
        len(dossier.hiring) == 12
        and dossier.hiring[-1].week_start == datetime(2032, 6, 14, tzinfo=UTC).date()
    )
    weeks = {w.week_start.isoformat(): w for w in dossier.hiring}
    assert weeks["2032-06-14"].new_offers == 1  # Job 2
    assert weeks["2032-06-07"].new_offers == 1  # Job 9 (Monday)
    assert weeks["2032-05-31"].new_offers == 1  # Job 10 (the Sunday before)
    assert weeks["2032-05-03"].new_offers == 1  # Job 40
    assert weeks["2032-06-14"].open_offers == 3  # Job 40 closed on May 27
    assert weeks["2032-05-03"].open_offers == 1 and weeks["2032-03-29"].open_offers == 0


async def test_offers_carry_the_inbox_state_and_the_follow_flag(db_session: AsyncSession) -> None:
    company = await make_company(db_session, "State Co")
    source = await make_source(db_session, company)
    posting, _ = await make_posting(db_session, source, first_seen_at=NOW - timedelta(days=1))
    opportunity = await make_opportunity(db_session, posting)
    item = JobInboxItem(
        owner_id=1,
        job_opportunity_id=opportunity.job_opportunity_id,
        state="ignored",
        is_shortlisted=True,
    )
    db_session.add(item)
    await db_session.flush()
    service = CompanyService(db_session, clock=lambda: NOW)
    before = await service.dossier(1, company.company_id, search_intent_id=None)
    assert (before.offers[0].state, before.offers[0].is_shortlisted) == ("ignored", True)
    # The owner can act on the offer from the dossier: it names the inbox item and its version.
    assert before.offers[0].job_inbox_item_id == item.job_inbox_item_id
    assert before.offers[0].version == item.version
    assert before.is_followed is False
    await service.set_followed(1, company.company_id, followed=True)
    assert (await service.dossier(1, company.company_id, search_intent_id=None)).is_followed


async def test_the_dossier_says_when_it_shows_only_the_best_offers(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("jobs_radar.services.companies.OFFER_LIMIT", 2)
    company = await make_company(db_session, "Many Offers Co")
    source = await make_source(db_session, company)
    for age in (1, 2, 3):
        posting, _ = await make_posting(db_session, source, first_seen_at=NOW - timedelta(days=age))
        await make_opportunity(db_session, posting)
    service = CompanyService(db_session, clock=lambda: NOW)
    dossier = await service.dossier(1, company.company_id, search_intent_id=None)
    assert len(dossier.offers) == 2 and dossier.offers_truncated is True
    monkeypatch.setattr("jobs_radar.services.companies.OFFER_LIMIT", 3)
    dossier = await service.dossier(1, company.company_id, search_intent_id=None)
    assert len(dossier.offers) == 3 and dossier.offers_truncated is False


async def test_an_unknown_company_is_404(db_session: AsyncSession) -> None:
    with pytest.raises(NotFoundError):
        await CompanyService(db_session, clock=lambda: NOW).dossier(
            1, 999_999, search_intent_id=None
        )


async def test_an_offer_without_an_inbox_item_has_nothing_to_act_on(
    db_session: AsyncSession,
) -> None:
    company = await make_company(db_session, "No Item Co")
    source = await make_source(db_session, company)
    posting, _ = await make_posting(db_session, source, first_seen_at=NOW - timedelta(days=1))
    await make_opportunity(db_session, posting)
    dossier = await CompanyService(db_session, clock=lambda: NOW).dossier(
        1, company.company_id, search_intent_id=None
    )
    offer = dossier.offers[0]
    assert (offer.job_inbox_item_id, offer.version, offer.state) == (None, None, None)
