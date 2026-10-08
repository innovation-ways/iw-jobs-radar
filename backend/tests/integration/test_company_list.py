"""Company list: new offers per window, relevant-only counts, sort and search (T7.1, document 13 s.9)."""

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
    unique,
)

from jobs_radar.db.models import CompanyAlias
from jobs_radar.domain.enums import LOCAL_OWNER_ID, Recommendation
from jobs_radar.services.companies import CompanyService

pytestmark = pytest.mark.integration

NOW = datetime(2031, 3, 1, 12, 0, tzinfo=UTC)  # far from other tests' data


class World:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tag = unique("cmp").lower()

    async def setup(self) -> "World":
        profile, self.profile_revision = await make_profile(self.session)
        self.intent, self.intent_revision = await make_intent(self.session, profile)
        return self

    async def company(self, name: str, offers: list[tuple[int, int | None, Recommendation]]) -> int:
        """A company with one opportunity per ``(age in days, fit or None, recommendation)``."""
        company = await make_company(self.session, f"{self.tag} {name}")
        source = await make_source(self.session, company)
        for age, fit, recommendation in offers:
            posting, snapshot = await make_posting(
                self.session, source, first_seen_at=NOW - timedelta(days=age)
            )
            await make_opportunity(self.session, posting)
            if fit is not None:
                extraction = await make_extraction(self.session, snapshot)
                await make_evaluation(
                    self.session,
                    snapshot,
                    extraction,
                    self.profile_revision,
                    self.intent_revision,
                    fit_score=fit,
                    recommendation=recommendation,
                )
        await self.session.flush()
        return company.company_id

    def service(self) -> CompanyService:
        return CompanyService(self.session, clock=lambda: NOW)

    async def list(self, **kwargs: object):  # type: ignore[no-untyped-def]
        return await self.service().list_companies(
            LOCAL_OWNER_ID,
            q=self.tag,
            search_intent_id=self.intent.search_intent_id,
            **kwargs,  # type: ignore[arg-type]
        )


R, N = Recommendation.RECOMMENDED, Recommendation.NOT_RECOMMENDED


async def test_new_offers_are_counted_per_window(db_session: AsyncSession) -> None:
    world = await (World(db_session)).setup()
    await world.company("Alpha", [(3, None, R), (10, None, R), (20, None, R), (40, None, R)])
    page = await world.list()
    row = page.rows[0]
    assert (row.new_offers_7d, row.new_offers_15d, row.new_offers_30d) == (1, 2, 3)
    assert row.open_offers == 4


async def test_relevant_offers_need_a_recommended_fit_at_or_above_the_threshold(
    db_session: AsyncSession,
) -> None:
    world = await (World(db_session)).setup()
    await world.company(
        "Beta",
        [(1, 90, R), (2, 45, R), (3, 44, R), (4, 99, N), (5, None, R)],
    )
    row = (await world.list()).rows[0]
    assert row.new_offers_7d == 5
    assert row.relevant_new_offers_7d == 2  # 90 and 45; 44 is too low, 99 is gated, one is unscored
    higher = (await world.list(relevance_min_score=60)).rows[0]
    assert higher.relevant_new_offers_7d == 1


async def test_without_an_intent_nothing_is_relevant(db_session: AsyncSession) -> None:
    world = await (World(db_session)).setup()
    await world.company("Gamma", [(1, 90, R)])
    page = await world.service().list_companies(LOCAL_OWNER_ID, q=world.tag, search_intent_id=None)
    assert page.rows[0].new_offers_7d == 1 and page.rows[0].relevant_new_offers_7d == 0


async def test_default_sort_is_new_offers_in_the_chosen_window_then_name(
    db_session: AsyncSession,
) -> None:
    world = await (World(db_session)).setup()
    await world.company("Few", [(2, None, R)])
    await world.company("Many", [(1, None, R), (2, None, R), (3, None, R)])
    await world.company("Old", [(25, None, R), (26, None, R), (27, None, R), (28, None, R)])
    week = [r.name.split(" ", 1)[1] for r in (await world.list(window=7)).rows]
    month = [r.name.split(" ", 1)[1] for r in (await world.list(window=30)).rows]
    assert week == ["Many", "Few", "Old"]
    assert month == ["Old", "Many", "Few"]


async def test_relevant_only_hides_companies_without_relevant_new_offers(
    db_session: AsyncSession,
) -> None:
    world = await (World(db_session)).setup()
    await world.company("Good", [(1, 80, R)])
    await world.company("Bad", [(1, 20, R)])
    names = [r.name.split(" ", 1)[1] for r in (await world.list(relevant_only=True)).rows]
    assert names == ["Good"]


async def test_sort_by_relevant_offers_and_by_name(db_session: AsyncSession) -> None:
    world = await (World(db_session)).setup()
    await world.company("Zed", [(1, 80, R), (2, 80, R)])
    await world.company("Alf", [(1, 80, R), (2, 10, R), (3, 10, R)])
    by_relevant = [r.name.split(" ", 1)[1] for r in (await world.list(sort="relevant")).rows]
    by_name = [r.name.split(" ", 1)[1] for r in (await world.list(sort="name")).rows]
    assert by_relevant == ["Zed", "Alf"] and by_name == ["Alf", "Zed"]


async def test_search_matches_names_and_aliases_and_pages(db_session: AsyncSession) -> None:
    world = await (World(db_session)).setup()
    one = await world.company("Search One", [(1, None, R)])
    await world.company("Search Two", [(1, None, R)])
    db_session.add(CompanyAlias(company_id=one, alias_normalised=f"{world.tag}-formerly-known"))
    await db_session.flush()
    by_alias = await world.service().list_companies(
        LOCAL_OWNER_ID, q=f"{world.tag}-formerly", search_intent_id=None
    )
    assert [r.company_id for r in by_alias.rows] == [one]
    page = await world.list(limit=1, offset=1)
    assert page.total == 2 and len(page.rows) == 1


async def test_closed_opportunities_do_not_count_as_open(db_session: AsyncSession) -> None:
    world = await (World(db_session)).setup()
    company = await make_company(db_session, f"{world.tag} Closed")
    source = await make_source(db_session, company)
    posting, _ = await make_posting(db_session, source, first_seen_at=NOW - timedelta(days=1))
    opportunity = await make_opportunity(db_session, posting)
    opportunity.closed_at = NOW
    await db_session.flush()
    row = (await world.list()).rows[0]
    assert row.open_offers == 0 and row.new_offers_7d == 1  # it was new, it is no longer open
