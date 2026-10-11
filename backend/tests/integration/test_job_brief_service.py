"""The briefing above a job's description: summary, technologies and key facts (ADR-059)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.evaluation_world import world
from tests.factories import make_company, make_extraction, make_posting, make_source

from jobs_radar.db.models import JobSummary
from jobs_radar.services.job_brief import JobBriefService

pytestmark = pytest.mark.integration

TEXT = "Acme is hiring a senior engineer, fully remote.\n\nThe posting does not state the pay."


def summary(snapshot_id: int, text: str | None = TEXT, **changes: object) -> JobSummary:
    values: dict[str, object] = {
        "job_snapshot_id": snapshot_id,
        "provider": "fixture",
        "model": "m1",
        "prompt_version": "summary-v1",
        "status": "succeeded" if text else "failed",
        "summary_text": text,
    }
    return JobSummary(**{**values, **changes})


async def test_without_a_summary_the_brief_has_none_but_still_lists_technologies_and_facts(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    brief = await JobBriefService(db_session).for_posting(w.posting.job_posting_id)
    assert brief.summary is None and brief.summary_model is None
    assert [t["name"] for t in brief.technologies] == ["Python", "API design"]
    assert brief.facts[:2] == ["Senior", "Remote"]


async def test_the_newest_good_summary_of_the_latest_snapshot_is_shown_with_its_model(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    db_session.add(summary(w.snapshot_id, "Older text, long enough to be a summary of this job."))
    await db_session.flush()
    db_session.add(summary(w.snapshot_id, model="m2"))
    db_session.add(summary(w.snapshot_id, None, model="m3"))  # a failed attempt never shows
    await db_session.flush()
    brief = await JobBriefService(db_session).for_posting(w.posting.job_posting_id)
    assert (brief.summary, brief.summary_model) == (TEXT, "m2")


async def test_a_job_without_an_extraction_still_gets_its_summary(
    db_session: AsyncSession,
) -> None:
    await world(db_session)
    source = await make_source(db_session, await make_company(db_session, "Bare Co"))
    posting, snapshot = await make_posting(db_session, source)
    await make_extraction(db_session, snapshot, attributes={})  # no output stored
    db_session.add(summary(snapshot.job_snapshot_id))
    await db_session.flush()
    brief = await JobBriefService(db_session).for_posting(posting.job_posting_id)
    assert brief.summary == TEXT and brief.technologies == [] and brief.facts == []
