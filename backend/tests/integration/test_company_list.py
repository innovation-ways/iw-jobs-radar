"""Company list: counted offers, best fit, follows, filters, sort and search (T7.1, ADR-053)."""

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

from jobs_radar.db.models import (
    CompanyAlias,
    CompanyEnrichmentCandidate,
    CompanyFollow,
    CompanyIgnore,
    JobInboxItem,
)
from jobs_radar.domain.enums import LOCAL_OWNER_ID, InboxState, Recommendation
from jobs_radar.repositories.schedule import ScheduleRepository
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

    async def company(
        self,
        name: str,
        offers: list[tuple[int, int | None, Recommendation]],
        *,
        ignored: tuple[int, ...] = (),
    ) -> int:
        """A company with one opportunity per ``(age in days, fit or None, recommendation)``.

        ``ignored`` lists the indexes of offers the owner ignored.
        """
        company = await make_company(self.session, f"{self.tag} {name}")
        source = await make_source(self.session, company)
        for index, (age, fit, recommendation) in enumerate(offers):
            posting, snapshot = await make_posting(
                self.session, source, first_seen_at=NOW - timedelta(days=age)
            )
            opportunity = await make_opportunity(self.session, posting)
            if index in ignored:
                self.session.add(
                    JobInboxItem(
                        owner_id=LOCAL_OWNER_ID,
                        job_opportunity_id=opportunity.job_opportunity_id,
                        state=InboxState.IGNORED.value,
                    )
                )
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


def names(page) -> list[str]:  # type: ignore[no-untyped-def]
    return [r.name.split(" ", 1)[1] for r in page.rows]


async def test_only_recent_open_offers_count_and_the_limit_is_configurable(
    db_session: AsyncSession,
) -> None:
    world = await (World(db_session)).setup()
    await world.company("Alpha", [(3, None, R), (20, None, R), (40, None, R)])
    row = (await world.list()).rows[0]
    assert row.open_offers == 2  # the 40-day-old offer is older than the default 30 days
    setting = await ScheduleRepository(db_session).get_or_create(LOCAL_OWNER_ID)
    setting.company_recency_days = 10
    await db_session.flush()
    assert (await world.list()).rows[0].open_offers == 1


async def test_recommended_offers_and_the_best_fit_use_the_threshold(
    db_session: AsyncSession,
) -> None:
    world = await (World(db_session)).setup()
    await world.company("Beta", [(1, 90, R), (2, 45, R), (3, 44, R), (4, 99, N), (5, None, R)])
    row = (await world.list()).rows[0]
    assert row.open_offers == 4  # the gated offer (99) is "Set aside" and is not counted
    assert row.recommended_offers == 2  # 90 and 45; 44 is too low, one is unscored
    assert row.best_fit_score == 90  # the best fit among the offers that are not set aside
    assert (await world.list(relevance_min_score=60)).rows[0].recommended_offers == 1


async def test_ignored_offers_do_not_count(db_session: AsyncSession) -> None:
    world = await (World(db_session)).setup()
    await world.company("Gamma", [(1, 95, R), (2, 70, R)], ignored=(0,))
    row = (await world.list()).rows[0]
    assert (row.open_offers, row.recommended_offers, row.best_fit_score) == (1, 1, 70)


async def test_without_an_intent_nothing_is_recommended(db_session: AsyncSession) -> None:
    world = await (World(db_session)).setup()
    await world.company("Delta", [(1, 90, R)])
    page = await world.service().list_companies(LOCAL_OWNER_ID, q=world.tag, search_intent_id=None)
    row = page.rows[0]
    assert (row.open_offers, row.recommended_offers, row.best_fit_score) == (1, 0, None)


async def test_sort_by_best_fit_or_name_with_followed_companies_first(
    db_session: AsyncSession,
) -> None:
    world = await (World(db_session)).setup()
    await world.company("Mid", [(1, 60, R)])
    await world.company("Top", [(1, 90, R)])
    await world.company("None", [(1, None, R)])
    watched = await world.company("Low", [(1, 35, R)])  # above the floor of 30
    assert names(await world.list(sort="fit")) == ["Top", "Mid", "Low", "None"]
    db_session.add(CompanyFollow(owner_id=LOCAL_OWNER_ID, company_id=watched))
    await db_session.flush()
    page = await world.list(sort="fit")
    assert names(page) == ["Low", "Top", "Mid", "None"]  # followed pinned on top
    assert [r.is_followed for r in page.rows] == [True, False, False, False]
    assert names(await world.list(sort="name")) == ["Low", "Mid", "None", "Top"]


async def test_sort_by_newest_offer_and_by_most_recommended_offers(
    db_session: AsyncSession,
) -> None:
    world = await (World(db_session)).setup()
    await world.company("Fresh", [(1, 50, R)])  # newest offer, one recommended
    await world.company("Busy", [(5, 90, R), (6, 80, R), (7, 70, R)])  # three recommended
    await world.company("Old", [(20, 99, R), (21, 99, R)])  # two recommended, oldest offers
    assert names(await world.list(sort="newest")) == ["Fresh", "Busy", "Old"]
    assert names(await world.list(sort="recommended")) == ["Busy", "Old", "Fresh"]


async def test_hide_ignored_companies_keeps_the_rest(db_session: AsyncSession) -> None:
    world = await (World(db_session)).setup()
    await world.company("Kept", [(1, 50, R)])
    muted = await world.company("Muted", [(1, 50, R)])
    db_session.add(CompanyIgnore(owner_id=LOCAL_OWNER_ID, company_id=muted))
    await db_session.flush()
    assert sorted(names(await world.list())) == ["Kept", "Muted"]
    assert names(await world.list(hide_ignored=True)) == ["Kept"]


async def test_ignored_only_lists_just_the_ignored_companies(db_session: AsyncSession) -> None:
    world = await (World(db_session)).setup()
    await world.company("Kept", [(1, 50, R)])
    muted = await world.company("Muted", [(1, 50, R)])
    db_session.add(CompanyIgnore(owner_id=LOCAL_OWNER_ID, company_id=muted))
    await db_session.flush()
    assert names(await world.list(ignored_only=True)) == ["Muted"]


async def test_open_filter_hides_companies_without_counted_offers_except_followed(
    db_session: AsyncSession,
) -> None:
    world = await (World(db_session)).setup()
    await world.company("Live", [(1, 50, R)])
    await world.company("Stale", [(60, 50, R)])
    await world.company("Muted", [(1, 50, R)], ignored=(0,))
    quiet = await world.company("Quiet", [(60, 50, R)])
    db_session.add(CompanyFollow(owner_id=LOCAL_OWNER_ID, company_id=quiet))
    await db_session.flush()
    assert names(await world.list(open_only=True)) == ["Quiet", "Live"]
    page = await world.list()
    assert page.total == 4


async def test_followed_recommended_and_pending_filters(db_session: AsyncSession) -> None:
    world = await (World(db_session)).setup()
    good = await world.company("Good", [(1, 80, R)])
    await world.company("Bad", [(1, 20, R)])
    unknown = await world.company("Unknown", [(1, None, R)])
    db_session.add(CompanyFollow(owner_id=LOCAL_OWNER_ID, company_id=good))
    db_session.add(
        CompanyEnrichmentCandidate(
            company_id=unknown,
            source_name="wikidata",
            external_id="Q1",
            label="Unknown Ltd",
            description=None,
            website=None,
            payload_json={},
        )
    )
    db_session.add(
        CompanyEnrichmentCandidate(
            company_id=good,
            source_name="wikidata",
            external_id="Q2",
            label="Rejected",
            description=None,
            website=None,
            payload_json={},
            status="rejected",
        )
    )
    await db_session.flush()
    assert names(await world.list(followed_only=True)) == ["Good"]
    assert names(await world.list(recommended_only=True)) == ["Good"]
    pending = await world.list(pending_only=True)
    assert names(pending) == ["Unknown"] and pending.rows[0].pending_candidates == 1


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
    assert (await world.list()).rows[0].open_offers == 0


async def test_offers_below_the_fit_floor_are_not_counted(db_session: AsyncSession) -> None:
    """A fit below the owner's floor is "Set aside" in the inbox and so not counted here."""
    world = await (World(db_session)).setup()
    await world.company("Floor", [(1, 10, R), (2, 50, R)])
    row = (await world.list()).rows[0]
    assert (row.open_offers, row.best_fit_score) == (1, 50)
