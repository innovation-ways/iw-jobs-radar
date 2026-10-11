"""The test sample of ADR-059: summarise the best-ranked open jobs and show the result."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.fake_provider import FakeProvider
from tests.inbox_scene import scene

from jobs_radar.domain.enums import LOCAL_OWNER_ID, InboxState
from jobs_radar.services.summary_sample import render_report, run_sample, top_postings

pytestmark = pytest.mark.integration

TEXT = "Acme is hiring a billing engineer. " + " ".join(["The role builds rating engines."] * 4)


async def test_the_best_ranked_unread_jobs_are_chosen_in_order(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    low = await s.entry(fit=40, title="Low")
    top = await s.entry(fit=90, title="Top")
    mid = await s.entry(fit=70, title="Mid")
    await s.entry(fit=95, title="Already read", state=InboxState.READ)
    await s.entry(title="Not evaluated")
    chosen = await top_postings(db_session, LOCAL_OWNER_ID, 2, company=s.tag)
    assert chosen == [(top.posting.job_posting_id, 90), (mid.posting.job_posting_id, 70)]
    assert low.posting.job_posting_id not in [posting_id for posting_id, _ in chosen]


async def test_the_sample_writes_each_summary_and_reports_it(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    a = await s.entry(fit=90, title="Alpha")
    provider = FakeProvider(responder=lambda request: {"summary": TEXT})
    rows = await run_sample(db_session, provider, [(a.posting.job_posting_id, 90)], max_chars=12000)
    (row,) = rows
    assert (row.title, row.fit, row.status, row.summary) == ("Alpha", 90, "written", TEXT)
    assert row.seconds >= 0
    again = await run_sample(
        db_session, provider, [(a.posting.job_posting_id, 90)], max_chars=12000
    )
    assert again[0].status == "already there" and len(provider.requests) == 1
    report = render_report(rows)
    assert "Alpha" in report and TEXT in report and "written" in report


async def test_an_unusable_answer_is_reported_and_the_sample_goes_on(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    a = await s.entry(fit=90, title="Alpha")
    b = await s.entry(fit=80, title="Beta")
    answers = iter([{"summary": "short"}, {"summary": "short"}, {"summary": TEXT}])
    provider = FakeProvider(responder=lambda request: next(answers))
    rows = await run_sample(
        db_session,
        provider,
        [(a.posting.job_posting_id, 90), (b.posting.job_posting_id, 80)],
        max_chars=12000,
    )
    assert [r.status for r in rows] == ["failed", "written"]
