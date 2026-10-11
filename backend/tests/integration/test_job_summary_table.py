"""The job-summary table: provenance, one success per inputs, append-only (ADR-059)."""

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.evaluation_world import world
from tests.factories import unique

from jobs_radar.db.models import JobSummary

pytestmark = pytest.mark.integration


def summary(snapshot_id: int, **changes: object) -> JobSummary:
    values: dict[str, object] = {
        "job_snapshot_id": snapshot_id,
        "provider": "fixture",
        "model": unique("m"),
        "prompt_version": "summary-v1",
        "status": "succeeded",
        "summary_text": "Acme is hiring an engineer. The posting does not state the pay.",
        "error_class": None,
        "latency_ms": 7,
    }
    return JobSummary(**{**values, **changes})


async def test_a_summary_is_stored_with_everything_that_produced_it(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    row = summary(w.snapshot_id)
    db_session.add(row)
    await db_session.flush()
    assert row.job_summary_id is not None and row.created_at is not None


async def test_the_same_success_cannot_be_stored_twice(db_session: AsyncSession) -> None:
    w = await world(db_session)
    first = summary(w.snapshot_id)
    db_session.add(first)
    await db_session.flush()
    db_session.add(summary(w.snapshot_id, model=first.model))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_failed_attempts_may_repeat(db_session: AsyncSession) -> None:
    w = await world(db_session)
    model = unique("m")
    for _ in range(2):
        db_session.add(
            summary(
                w.snapshot_id,
                model=model,
                status="failed",
                summary_text=None,
                error_class="invalid_output",
            )
        )
    await db_session.flush()


async def test_a_success_needs_its_text(db_session: AsyncSession) -> None:
    w = await world(db_session)
    db_session.add(summary(w.snapshot_id, summary_text=None))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_an_unknown_status_is_refused(db_session: AsyncSession) -> None:
    w = await world(db_session)
    db_session.add(summary(w.snapshot_id, status="great"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_summary_can_never_be_changed(db_session: AsyncSession) -> None:
    w = await world(db_session)
    row = summary(w.snapshot_id)
    db_session.add(row)
    await db_session.flush()
    row.summary_text = "Edited"
    with pytest.raises(DBAPIError, match="append-only"):
        await db_session.flush()
