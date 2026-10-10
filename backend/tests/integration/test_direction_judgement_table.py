"""The direction-judgement table and the direction basis of evaluations (ADR-057)."""

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.evaluation_world import world
from tests.factories import unique

from jobs_radar.db.models import DirectionJudgement

pytestmark = pytest.mark.integration


def judgement(snapshot_id: int, **changes: object) -> DirectionJudgement:
    values: dict[str, object] = {
        "job_snapshot_id": snapshot_id,
        "direction_hash": "sha256:" + "a" * 64,
        "direction_label": "Billing SME",
        "provider": "fixture",
        "model": unique("m"),
        "prompt_version": "direction-v1",
        "level": "strong",
        "job_quote": "Design billing platforms",
        "direction_quote": "billing SME",
    }
    return DirectionJudgement(**{**values, **changes})


async def test_a_judgement_is_stored_with_everything_that_produced_it(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    row = judgement(w.snapshot_id)
    db_session.add(row)
    await db_session.flush()
    assert row.direction_judgement_id is not None and row.created_at is not None


async def test_the_same_judgement_cannot_be_stored_twice(db_session: AsyncSession) -> None:
    w = await world(db_session)
    first = judgement(w.snapshot_id)
    db_session.add(first)
    await db_session.flush()
    db_session.add(judgement(w.snapshot_id, model=first.model))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_an_unknown_level_is_refused(db_session: AsyncSession) -> None:
    w = await world(db_session)
    db_session.add(judgement(w.snapshot_id, level="great"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_judgement_can_never_be_changed(db_session: AsyncSession) -> None:
    w = await world(db_session)
    row = judgement(w.snapshot_id)
    db_session.add(row)
    await db_session.flush()
    row.level = "none"
    with pytest.raises(DBAPIError, match="append-only"):
        await db_session.flush()
