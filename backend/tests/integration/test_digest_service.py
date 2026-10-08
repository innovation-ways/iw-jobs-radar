"""The daily digest: new high-fit jobs, changed shortlisted jobs and source health (T5.4)."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import make_company, make_source
from tests.inbox_scene import T0, Scene, scene

from jobs_radar.db.models import CollectionRun, JobChangeEvent, SourceConfiguration, SourceRunResult
from jobs_radar.domain.enums import LOCAL_OWNER_ID, InboxState, Recommendation
from jobs_radar.services.digest import DigestService

pytestmark = pytest.mark.integration

# Far from the dates other tests use, so only this test's jobs fall in the window.
BASE = T0 + timedelta(days=2000)
NOW = BASE + timedelta(hours=20)


def digest(session: AsyncSession, s: Scene) -> DigestService:
    return DigestService(session, clock=lambda: NOW)


async def build(session: AsyncSession, s: Scene):  # type: ignore[no-untyped-def]
    return await digest(session, s).build(
        LOCAL_OWNER_ID, search_intent_id=s.intent.search_intent_id
    )


def ids(items: list) -> list[int]:  # type: ignore[type-arg]
    return [row.item.job_inbox_item_id for row in items]


# --- new high-fit ----------------------------------------------------------------------------------


async def test_new_high_fit_jobs_are_those_first_seen_in_the_window_at_or_above_the_alert_threshold(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    day = (NOW - T0).days  # days offset of "today" relative to T0
    high = await s.entry(fit=90, days=day)
    higher = await s.entry(fit=95, days=day)
    at_threshold = await s.entry(fit=65, days=day)
    low = await s.entry(fit=64, days=day)
    old = await s.entry(fit=99, days=day - 3)
    unscored = await s.entry(days=day)
    gated = await s.entry(fit=99, days=day, recommendation=Recommendation.NOT_RECOMMENDED)
    ignored = await s.entry(fit=99, days=day, state=InboxState.IGNORED)
    result = await build(db_session, s)
    assert ids(result.new_high_fit) == [
        e.item.job_inbox_item_id for e in (higher, high, at_threshold)
    ]
    excluded = {e.item.job_inbox_item_id for e in (low, old, unscored, gated, ignored)}
    assert not excluded & set(ids(result.new_high_fit))
    assert result.alert_threshold == 65


async def test_without_an_intent_there_are_no_scores_but_the_digest_still_works(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    result = await digest(db_session, s).build(LOCAL_OWNER_ID, search_intent_id=None)
    assert result.counts["new_high_fit"] >= 0 and result.generated_at == NOW


# --- shortlisted jobs that changed --------------------------------------------------------------------


async def test_shortlisted_jobs_that_changed_in_the_window_are_listed_with_what_changed(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    day = (NOW - T0).days
    changed = await s.entry(shortlisted=True, days=day - 5)
    old_change = await s.entry(shortlisted=True, days=day - 5)
    not_starred = await s.entry(days=day - 5)
    for entry, when in (
        (changed, NOW - timedelta(hours=3)),
        (old_change, NOW - timedelta(days=4)),
        (not_starred, NOW - timedelta(hours=1)),
    ):
        db_session.add(
            JobChangeEvent(
                job_posting_id=entry.posting.job_posting_id,
                to_job_snapshot_id=(await _snapshot(db_session, entry)),
                changed_fields=["title", "description"],
                is_material=True,
                created_at=when,
            )
        )
    await db_session.flush()
    result = await build(db_session, s)
    mine = [
        c
        for c in result.changed_shortlisted
        if c.row.item.job_inbox_item_id
        in {
            changed.item.job_inbox_item_id,
            old_change.item.job_inbox_item_id,
            not_starred.item.job_inbox_item_id,
        }
    ]
    assert [c.row.item.job_inbox_item_id for c in mine] == [changed.item.job_inbox_item_id]
    assert mine[0].changed_fields == ["title", "description"] and mine[
        0
    ].changed_at == NOW - timedelta(hours=3)


async def _snapshot(session: AsyncSession, entry) -> int:  # type: ignore[no-untyped-def]
    from sqlalchemy import select

    from jobs_radar.db.models import JobSnapshot

    return int(
        (
            await session.execute(
                select(JobSnapshot.job_snapshot_id).where(
                    JobSnapshot.job_posting_id == entry.posting.job_posting_id
                )
            )
        ).scalar_one()
    )


# --- source health -----------------------------------------------------------------------------------------


async def add_result(
    session: AsyncSession,
    source: SourceConfiguration,
    outcome: str,
    finished: datetime,
    error_class: str | None = None,
) -> None:
    run = CollectionRun(owner_id=LOCAL_OWNER_ID, trigger="manual", status="succeeded")
    session.add(run)
    await session.flush()
    session.add(
        SourceRunResult(
            collection_run_id=run.collection_run_id,
            source_configuration_id=source.source_configuration_id,
            started_at=finished,
            finished_at=finished,
            outcome=outcome,
            duration_ms=10,
            error_class=error_class,
            error_message="The board was not found." if error_class else None,
        )
    )
    await session.flush()


async def test_sources_needing_attention_are_listed_with_the_reason(
    db_session: AsyncSession,
) -> None:
    from sqlalchemy import update

    s = await scene(db_session)
    await db_session.execute(update(SourceConfiguration).values(enabled=False))
    company = await make_company(db_session)
    failing = await make_source(db_session, company)
    stale = await make_source(db_session, company)
    never = await make_source(db_session, company)
    healthy = await make_source(db_session, company)
    disabled = await make_source(db_session, company)
    disabled.enabled = False
    for source in (failing, stale, never, healthy):
        source.enabled = True
    await add_result(db_session, failing, "failed", NOW - timedelta(hours=2), "not_found")
    await add_result(db_session, stale, "success", NOW - timedelta(hours=60))
    await add_result(db_session, healthy, "success", NOW - timedelta(hours=5))
    await add_result(db_session, disabled, "failed", NOW - timedelta(hours=1), "timeout")
    result = await build(db_session, s)
    by_id = {h.source_configuration_id: h for h in result.source_health}
    assert set(by_id) == {
        failing.source_configuration_id,
        stale.source_configuration_id,
        never.source_configuration_id,
    }
    assert (
        by_id[failing.source_configuration_id].status,
        by_id[failing.source_configuration_id].error_class,
    ) == ("failed", "not_found")
    assert by_id[stale.source_configuration_id].status == "stale"
    assert by_id[never.source_configuration_id].status == "never_run"
    assert result.counts["sources_needing_attention"] == 3


async def test_the_digest_reports_the_last_run(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    run = CollectionRun(
        owner_id=LOCAL_OWNER_ID,
        trigger="scheduled",
        status="partial",
        finished_at=NOW - timedelta(minutes=5),
    )
    db_session.add(run)
    await db_session.flush()
    result = await build(db_session, s)
    assert (
        result.last_run is not None and result.last_run.collection_run_id == run.collection_run_id
    )
