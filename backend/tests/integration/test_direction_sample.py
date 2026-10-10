"""The test sample of ADR-057: judge chosen jobs and show what a weight would do."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.evaluation_world import world
from tests.fake_provider import FakeProvider
from tests.integration.test_direction_evaluation import AI, BILLING, directions, with_directions

from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.services.direction_sample import render_report, run_sample

pytestmark = pytest.mark.integration

GOOD = {
    "level": "strong",
    "job_quote": "large enterprises in finance and telecom",
    "direction_quote": "billing SME",
}
WHAT_IF = {"career_direction": 40, "role_responsibilities": 5}


async def test_the_sample_shows_the_judgements_and_the_what_if_score(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    posting_id = w.posting.job_posting_id
    await with_directions(
        db_session,
        w,
        directions(("Billing SME", BILLING, True), ("AI engineer", AI, True)),
        weight=0,
    )
    provider = FakeProvider(
        responder=lambda request: GOOD if "Billing SME" in request.user else {"level": "none"}
    )
    rows = await run_sample(
        db_session, provider, LOCAL_OWNER_ID, [posting_id], max_chars=12000, what_if=WHAT_IF
    )
    row = rows[0]
    assert row.job_posting_id == posting_id
    assert row.levels == {"Billing SME": "strong", "AI engineer": "none"}
    assert row.winner == "Billing SME"
    assert row.before_fit == row.after_fit  # the weight is 0: the score does not change
    assert row.what_if_fit is not None and row.what_if_fit != row.after_fit
    assert row.job_quote == "large enterprises in finance and telecom"


async def test_a_job_that_was_not_extracted_is_reported_as_skipped(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session, with_extraction=False)
    await with_directions(db_session, w, directions(("Billing SME", BILLING, True)), weight=0)
    rows = await run_sample(
        db_session,
        FakeProvider(responder=lambda request: GOOD),
        LOCAL_OWNER_ID,
        [w.posting.job_posting_id],
        max_chars=12000,
        what_if=WHAT_IF,
    )
    assert rows[0].skipped is not None and "extract" in rows[0].skipped


async def test_the_report_is_a_readable_table() -> None:
    from jobs_radar.services.direction_sample import SampleRow

    row = SampleRow(
        job_posting_id=7,
        company="Acme",
        title="Billing Architect",
        before_fit=40,
        after_fit=40,
        what_if_fit=58,
        winner="Billing SME",
        levels={"Billing SME": "strong"},
        job_quote="billing platform",
        skipped=None,
    )
    report = render_report([row], WHAT_IF)
    assert "Billing Architect" in report and "Acme" in report
    assert "40" in report and "58" in report and "strong" in report
    assert "career_direction=40" in report
