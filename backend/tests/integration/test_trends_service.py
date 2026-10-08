"""Weekly trend aggregation and report: relevant jobs only, shares, markers, merged terms (T7.5, T7.6)."""

from datetime import UTC, date, datetime, timedelta
from secrets import token_hex
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.data import sample_extraction_output
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
    IntentRevision,
    Skill,
    SourceConfiguration,
    TaxonomyTerm,
    TrendWeekly,
)
from jobs_radar.domain.enums import LOCAL_OWNER_ID, Recommendation
from jobs_radar.services.trends import TrendService

pytestmark = pytest.mark.integration

NOW = datetime(2033, 3, 16, 12, 0, tzinfo=UTC)  # Wednesday; this week starts 2033-03-14
THIS_WEEK = date(2033, 3, 14)
R, N = Recommendation.RECOMMENDED, Recommendation.NOT_RECOMMENDED


class World:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def setup(self) -> "World":
        self.profile, self.profile_revision = await make_profile(self.session)
        self.intent, self.revision = await make_intent(self.session, self.profile)
        self.company = await make_company(self.session)
        self.source = await make_source(self.session, self.company)
        self.source.created_at = NOW - timedelta(days=200)
        return self

    async def skill(self, name: str) -> int:
        skill = Skill(canonical_name=f"{name}-{unique('s')}", kind="technology")
        self.session.add(skill)
        await self.session.flush()
        return skill.skill_id

    async def job(
        self,
        age_days: int,
        *,
        fit: int = 80,
        recommendation: Recommendation = R,
        closed_after_days: int | None = None,
        role: str = "ai_solutions_engineering",
        work_mode: str = "remote",
        skills: list[int] | None = None,
    ) -> None:
        posting, snapshot = await make_posting(
            self.session, self.source, first_seen_at=NOW - timedelta(days=age_days)
        )
        opportunity = await make_opportunity(self.session, posting)
        if closed_after_days is not None:
            opportunity.closed_at = opportunity.first_seen_at + timedelta(days=closed_after_days)
        output: dict[str, Any] = sample_extraction_output()
        output["role_families"][0]["key"] = role
        output["work_mode"]["value"] = work_mode
        extraction = await make_extraction(
            self.session,
            snapshot,
            attributes={
                "output": output,
                "skills_resolved": [
                    {"skill_id": i, "name": f"s{i}", "importance": "must"} for i in skills or []
                ],
                "locations_resolved": [],
            },
        )
        await make_evaluation(
            self.session,
            snapshot,
            extraction,
            self.profile_revision,
            self.revision,
            fit_score=fit,
            recommendation=recommendation,
        )

    def service(self) -> TrendService:
        return TrendService(self.session, clock=lambda: NOW)

    async def rows(self, kind: str, key: str) -> dict[date, TrendWeekly]:
        found = (
            await self.session.execute(
                select(TrendWeekly).where(
                    TrendWeekly.search_intent_id == self.intent.search_intent_id,
                    TrendWeekly.term_kind == kind,
                    TrendWeekly.term_key == key,
                )
            )
        ).scalars()
        return {r.week_start: r for r in found}


@pytest.fixture(autouse=True)
async def isolate(db_session: AsyncSession) -> None:
    # Other tests' sources would join the source set; only this test's source is enabled.
    await db_session.execute(update(SourceConfiguration).values(enabled=False))


async def test_only_relevant_jobs_are_counted_and_openness_follows_the_lifecycle(
    db_session: AsyncSession,
) -> None:
    world = await World(db_session).setup()
    await world.job(1, fit=90)  # this week, open
    await world.job(10, fit=60, closed_after_days=2)  # last week's week-before: closed on day 8
    await world.job(10, fit=44)  # below the threshold
    await world.job(5, fit=95, recommendation=N)  # gated
    await world.service().recompute(LOCAL_OWNER_ID, world.intent.search_intent_id)
    rows = await world.rows("role_family", "ai_solutions_engineering")
    this, previous = rows[THIS_WEEK], rows[THIS_WEEK - timedelta(weeks=1)]
    assert (this.open_count, this.new_count, this.relevant_total_open) == (1, 1, 1)
    assert this.relevance_min_score == 45
    # the job seen 10 days ago (Sunday Mar 6, week of Feb 28) was closed on Mar 8 (week of Mar 7)
    seen_week = rows[THIS_WEEK - timedelta(weeks=2)]
    assert (seen_week.new_count, seen_week.open_count, seen_week.closed_count) == (1, 1, 0)
    assert (previous.new_count, previous.open_count, previous.closed_count) == (0, 0, 1)
    assert previous.relevant_total_open == 0


async def test_terms_of_every_kind_are_counted(db_session: AsyncSession) -> None:
    world = await World(db_session).setup()
    python, sql = await world.skill("python"), await world.skill("sql")
    await world.job(1, skills=[python, sql], role="ai_ml_engineering", work_mode="hybrid")
    await world.job(2, skills=[python])
    await world.service().recompute(LOCAL_OWNER_ID, world.intent.search_intent_id)
    assert (await world.rows("skill", str(python)))[THIS_WEEK].open_count == 2
    assert (await world.rows("skill", str(sql)))[THIS_WEEK].open_count == 1
    assert (await world.rows("role_family", "ai_ml_engineering"))[THIS_WEEK].open_count == 1
    assert (await world.rows("work_arrangement", "hybrid"))[THIS_WEEK].open_count == 1
    assert (await world.rows("work_arrangement", "remote"))[THIS_WEEK].open_count == 1
    assert (await world.rows("seniority_level", "senior"))[THIS_WEEK].open_count == 2
    assert (await world.rows("sector", "enterprise_it"))[THIS_WEEK].open_count == 2
    assert (await world.rows("engagement_type", "contractor_b2b"))[THIS_WEEK].open_count == 2


async def test_recomputing_is_idempotent_and_later_runs_only_touch_recent_weeks(
    db_session: AsyncSession,
) -> None:
    world = await World(db_session).setup()
    await world.job(30)
    service = world.service()
    first = await service.recompute(LOCAL_OWNER_ID, world.intent.search_intent_id)
    count = len(
        (
            await db_session.execute(
                select(TrendWeekly).where(
                    TrendWeekly.search_intent_id == world.intent.search_intent_id
                )
            )
        )
        .scalars()
        .all()
    )
    second = await service.recompute(LOCAL_OWNER_ID, world.intent.search_intent_id)
    again = len(
        (
            await db_session.execute(
                select(TrendWeekly).where(
                    TrendWeekly.search_intent_id == world.intent.search_intent_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert count == again and first > second > 0  # backfill once, then just the last two weeks


async def test_a_merged_taxonomy_term_continues_on_one_line(db_session: AsyncSession) -> None:
    world = await World(db_session).setup()
    old, new = f"old_role_{token_hex(3)}", f"new_role_{token_hex(3)}"
    new_term = TaxonomyTerm(
        kind="role_family",
        term_key=new,
        label="New role",
        origin="seed",
        introduced_in_taxonomy_version_id=1,
    )
    db_session.add(new_term)
    await db_session.flush()
    db_session.add(
        TaxonomyTerm(
            kind="role_family",
            term_key=old,
            label="Old role",
            origin="seed",
            introduced_in_taxonomy_version_id=1,
            replaced_by_taxonomy_term_id=new_term.taxonomy_term_id,
        )
    )
    await db_session.flush()
    await world.job(2, role=old)
    await world.job(3, role=new)
    await world.service().recompute(LOCAL_OWNER_ID, world.intent.search_intent_id)
    assert (await world.rows("role_family", new))[THIS_WEEK].open_count == 2
    assert await world.rows("role_family", old) == {}


async def test_the_report_has_shares_changes_periods_and_the_history_notice(
    db_session: AsyncSession,
) -> None:
    world = await World(db_session).setup()
    for age in (1, 2, 9, 16, 17, 18):
        await world.job(age, role="ai_solutions_engineering" if age < 17 else "data_engineering")
    service = world.service()
    await service.recompute(LOCAL_OWNER_ID, world.intent.search_intent_id)
    report = await service.report(
        LOCAL_OWNER_ID, world.intent.search_intent_id, kind="role_family", weeks=4
    )
    assert report.relevance_min_score == 45 and report.available_weeks >= 3
    assert report.first_week <= THIS_WEEK - timedelta(weeks=2)
    assert (report.periods[0].key, report.periods[0].available) == (
        "4w",
        report.available_weeks >= 4,
    )
    assert [p.available for p in report.periods][1:] == [
        False,
        False,
    ]  # 12 weeks and 6 months stay locked
    top = report.rows[0]
    assert top.term_key == "ai_solutions_engineering" and top.label
    last = top.series[-1]
    assert last.week_start == THIS_WEEK and last.open_count == 4 and last.share == 4 / 6
    assert top.open_now == 4 and top.share_now == 4 / 6
    assert len(report.weeks) == min(4, report.available_weeks)


async def test_a_new_source_and_a_new_intent_revision_mark_the_chart(
    db_session: AsyncSession,
) -> None:
    world = await World(db_session).setup()
    await world.job(1)
    await world.job(20)
    service = world.service()
    # a source created last week changes the source set from that week on
    extra = await make_source(db_session, world.company)
    extra.created_at = NOW - timedelta(days=5)
    extra.enabled = True
    world.source.enabled = True
    await db_session.flush()
    await service.recompute(LOCAL_OWNER_ID, world.intent.search_intent_id)
    report = await service.report(
        LOCAL_OWNER_ID, world.intent.search_intent_id, kind="role_family", weeks=4
    )
    assert report.source_set_changes == [THIS_WEEK - timedelta(weeks=1)]
    assert report.intent_revision_changes == []

    # a new intent revision: the next recompute writes this week under it and the report flags the change
    revision = IntentRevision(
        search_intent_id=world.intent.search_intent_id,
        revision_number=2,
        intent_json=world.revision.intent_json,
    )
    db_session.add(revision)
    await db_session.flush()
    world.intent.current_intent_revision_id = revision.intent_revision_id
    await db_session.flush()
    await service.recompute(LOCAL_OWNER_ID, world.intent.search_intent_id)
    after = await service.report(
        LOCAL_OWNER_ID, world.intent.search_intent_id, kind="role_family", weeks=4
    )
    assert after.intent_revision_changes == [THIS_WEEK - timedelta(weeks=1)]


async def test_an_intent_without_relevant_jobs_gives_an_empty_report(
    db_session: AsyncSession,
) -> None:
    world = await World(db_session).setup()
    await world.job(2, fit=10)
    service = world.service()
    await service.recompute(LOCAL_OWNER_ID, world.intent.search_intent_id)
    report = await service.report(
        LOCAL_OWNER_ID, world.intent.search_intent_id, kind="skill", weeks=12
    )
    assert report.rows == []


async def test_the_runner_recomputes_enabled_intents_only_when_due(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.factories import session_factory_for

    from jobs_radar.services.trends import TrendRunner

    world = await World(db_session).setup()
    await world.job(2)
    factory = session_factory_for(db_session, monkeypatch)
    intent_id = world.intent.search_intent_id
    runner = TrendRunner(factory, clock=lambda: NOW)
    assert await runner.run_due(LOCAL_OWNER_ID, only_intent=intent_id) > 0
    assert await runner.run_due(LOCAL_OWNER_ID, only_intent=intent_id) == 0  # fresh
    later = TrendRunner(factory, clock=lambda: NOW + timedelta(hours=25))
    assert await later.run_due(LOCAL_OWNER_ID, only_intent=intent_id) > 0
    world.intent.enabled = False
    await db_session.flush()
    stale = TrendRunner(factory, clock=lambda: NOW + timedelta(days=3))
    assert await stale.run_due(LOCAL_OWNER_ID, only_intent=intent_id) == 0  # disabled
