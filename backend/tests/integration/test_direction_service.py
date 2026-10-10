"""Judging jobs against the owner's career directions and re-scoring them (ADR-057)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.data import SAMPLE_JOB_DESCRIPTION, SAMPLE_JOB_TITLE, sample_extraction_output
from tests.evaluation_world import World, world
from tests.factories import make_company, make_extraction, make_posting, make_source, unique
from tests.fake_provider import FakeProvider
from tests.integration.test_direction_evaluation import AI, BILLING, directions, with_directions

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import DirectionJudgement, MatchEvaluation
from jobs_radar.domain.enums import LOCAL_OWNER_ID, ProviderErrorClass
from jobs_radar.repositories.evaluations import EvaluationRepository
from jobs_radar.services.direction_service import DirectionService, DirectionUnavailable

pytestmark = pytest.mark.integration

GOOD = {
    "level": "strong",
    "job_quote": "large enterprises in finance and telecom",
    "direction_quote": "billing SME",
}


def service(session: AsyncSession, provider: FakeProvider) -> DirectionService:
    return DirectionService(session, provider, max_chars=12000)


def answering(level: str = "strong") -> FakeProvider:
    return FakeProvider(responder=lambda request: {**GOOD, "level": level})


async def count(session: AsyncSession, model: type, **filters: Any) -> int:
    statement = select(func.count()).select_from(model)
    for column, value in filters.items():
        statement = statement.where(getattr(model, column) == value)
    return int((await session.execute(statement)).scalar_one())


async def ready(session: AsyncSession, *items: tuple[str, str, bool]) -> World:
    w = await world(session)
    await with_directions(session, w, directions(*items))
    return w


async def test_assessing_a_job_judges_each_enabled_direction_and_scores_it_again(
    db_session: AsyncSession,
) -> None:
    w = await ready(db_session, ("Billing SME", BILLING, True), ("AI engineer", AI, True))
    provider = answering()
    summary = await service(db_session, provider).assess(LOCAL_OWNER_ID, w.posting.job_posting_id)
    assert (summary.judged, summary.evaluated) == (2, 1)
    assert len(provider.requests) == 2
    assert await count(db_session, DirectionJudgement, job_snapshot_id=w.snapshot_id) == 2
    latest = (
        (
            await db_session.execute(
                select(MatchEvaluation)
                .where(MatchEvaluation.job_snapshot_id == w.snapshot_id)
                .order_by(MatchEvaluation.match_evaluation_id.desc())
            )
        )
        .scalars()
        .first()
    )
    assert latest is not None and latest.direction_basis.startswith("sha256:")


async def test_assessing_twice_calls_the_model_only_once_per_direction(
    db_session: AsyncSession,
) -> None:
    w = await ready(db_session, ("Billing SME", BILLING, True))
    provider = answering()
    first = await service(db_session, provider).assess(LOCAL_OWNER_ID, w.posting.job_posting_id)
    again = await service(db_session, provider).assess(LOCAL_OWNER_ID, w.posting.job_posting_id)
    assert (first.judged, again.judged) == (1, 0)
    assert len(provider.requests) == 1


async def test_a_disabled_direction_is_never_sent_to_the_model(db_session: AsyncSession) -> None:
    w = await ready(db_session, ("Billing SME", BILLING, True), ("AI engineer", AI, False))
    provider = answering()
    await service(db_session, provider).assess(LOCAL_OWNER_ID, w.posting.job_posting_id)
    assert len(provider.requests) == 1 and "Billing SME" in provider.requests[0].user


async def test_without_enabled_directions_nothing_is_judged(db_session: AsyncSession) -> None:
    w = await ready(db_session, ("Billing SME", BILLING, False))
    provider = answering()
    summary = await service(db_session, provider).assess(LOCAL_OWNER_ID, w.posting.job_posting_id)
    assert (summary.judged, summary.evaluated) == (0, 0) and provider.requests == []


async def test_an_answer_that_stays_invalid_is_stored_as_unknown_so_it_is_not_retried(
    db_session: AsyncSession,
) -> None:
    w = await ready(db_session, ("Billing SME", BILLING, True))
    provider = FakeProvider(["not json", "still not json"])
    summary = await service(db_session, provider).assess(LOCAL_OWNER_ID, w.posting.job_posting_id)
    assert summary.judged == 1
    row = (
        await db_session.execute(
            select(DirectionJudgement).where(DirectionJudgement.job_snapshot_id == w.snapshot_id)
        )
    ).scalar_one()
    assert (row.level, row.job_quote) == ("unknown", None)


async def test_an_unavailable_model_raises_and_stores_nothing(db_session: AsyncSession) -> None:
    w = await ready(db_session, ("Billing SME", BILLING, True))
    provider = FakeProvider([ProviderError(ProviderErrorClass.UNAVAILABLE, "down")])
    with pytest.raises(DirectionUnavailable):
        await service(db_session, provider).assess(LOCAL_OWNER_ID, w.posting.job_posting_id)
    assert await count(db_session, DirectionJudgement, job_snapshot_id=w.snapshot_id) == 0


async def test_an_unknown_or_unextracted_job_cannot_be_assessed(db_session: AsyncSession) -> None:
    w = await ready(db_session, ("Billing SME", BILLING, True))
    with pytest.raises(NotFoundError):
        await service(db_session, answering()).assess(LOCAL_OWNER_ID, 999_999_999)
    source = await make_source(db_session, await make_company(db_session, unique("Co")))
    bare, _ = await make_posting(db_session, source)
    summary = await service(db_session, answering()).assess(LOCAL_OWNER_ID, bare.job_posting_id)
    assert (summary.judged, summary.evaluated) == (0, 0)
    assert w.posting.job_posting_id != bare.job_posting_id


async def new_job(session: AsyncSession, w: World, seen: datetime):  # type: ignore[no-untyped-def]
    """An extracted job first seen at ``seen``."""
    source = await make_source(session, await make_company(session, unique("Acme")))
    posting, snapshot = await make_posting(
        session,
        source,
        title=SAMPLE_JOB_TITLE,
        description=SAMPLE_JOB_DESCRIPTION,
        first_seen_at=seen,
    )
    await make_extraction(
        session,
        snapshot,
        attributes={
            "output": sample_extraction_output(),
            "unverified": [],
            "dropped_keys": [],
            "contradictions": [],
            "skills_resolved": [],
            "locations_resolved": [],
        },
    )
    return posting, snapshot


async def test_the_worker_judges_only_jobs_first_seen_after_the_first_direction_was_saved(
    db_session: AsyncSession,
) -> None:
    w = await ready(db_session, ("Billing SME", BILLING, True))
    later = datetime.now(UTC) + timedelta(hours=1)
    posting, snapshot = await new_job(db_session, w, later)
    provider = answering()
    judged = await service(db_session, provider).run_pending(limit=10)
    assert judged == 1  # the new job; the older one of the world is left alone
    assert (
        await count(db_session, DirectionJudgement, job_snapshot_id=snapshot.job_snapshot_id) == 1
    )
    assert await count(db_session, DirectionJudgement, job_snapshot_id=w.snapshot_id) == 0
    assert await service(db_session, provider).run_pending(limit=10) == 0
    assert posting.job_posting_id is not None


async def test_judging_again_with_another_model_adds_judgements_and_the_newest_counts(
    db_session: AsyncSession,
) -> None:
    w = await ready(db_session, ("Billing SME", BILLING, True))
    posting_id = w.posting.job_posting_id
    first = FakeProvider(responder=lambda request: {**GOOD, "level": "weak"}, model="small")
    second = FakeProvider(responder=lambda request: {**GOOD, "level": "strong"}, model="large")
    await service(db_session, first).assess(LOCAL_OWNER_ID, posting_id)
    again = await service(db_session, second).assess(LOCAL_OWNER_ID, posting_id, rejudge=True)
    assert again.judged == 1 and len(second.requests) == 1
    assert await count(db_session, DirectionJudgement, job_snapshot_id=w.snapshot_id) == 2
    latest = (
        (
            await db_session.execute(
                select(MatchEvaluation)
                .where(MatchEvaluation.job_snapshot_id == w.snapshot_id)
                .order_by(MatchEvaluation.match_evaluation_id.desc())
            )
        )
        .scalars()
        .first()
    )
    assert latest is not None
    dimension = next(
        d
        for d in await EvaluationRepository(db_session).dimensions(latest.match_evaluation_id)
        if d.dimension_key == "career_direction"
    )
    assert dimension.quality == "strong"  # the large model's judgement is the one scored


async def test_without_rejudging_a_judged_job_is_left_alone(db_session: AsyncSession) -> None:
    w = await ready(db_session, ("Billing SME", BILLING, True))
    posting_id = w.posting.job_posting_id
    await service(db_session, FakeProvider(responder=lambda r: GOOD, model="a")).assess(
        LOCAL_OWNER_ID, posting_id
    )
    other = FakeProvider(responder=lambda r: GOOD, model="b")
    result = await service(db_session, other).assess(LOCAL_OWNER_ID, posting_id)
    assert result.judged == 0 and other.requests == []
