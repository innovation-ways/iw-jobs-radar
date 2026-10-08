"""The extraction queue: enqueue, claim, process and finalise (T4.4)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.data import SAMPLE_JOB_DESCRIPTION, SAMPLE_JOB_TITLE, sample_extraction_output
from tests.factories import make_company, make_posting, make_source, session_factory_for
from tests.fake_provider import FakeProvider

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.db.models import JobExtraction, JobPosting, Skill
from jobs_radar.domain.enums import ProviderErrorClass
from jobs_radar.schemas.extraction import ExtractionOutput
from jobs_radar.services.extraction_queue import ExtractionQueue

pytestmark = pytest.mark.integration

T0 = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture(autouse=True)
async def _only_this_tests_jobs(db_session: AsyncSession) -> None:
    """Close postings committed by earlier tests so only this test's jobs are queued."""
    await db_session.execute(
        update(JobPosting).where(JobPosting.closed_at.is_(None)).values(closed_at=T0)
    )


def queue(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    provider: FakeProvider,
    clock: Clock | None = None,
    **options: Any,
) -> ExtractionQueue:
    return ExtractionQueue(
        session_factory_for(session, monkeypatch),
        provider,
        max_chars=options.pop("max_chars", 12000),
        clock=clock or Clock(),
        **options,
    )


async def job(session: AsyncSession, **kwargs: Any):  # type: ignore[no-untyped-def]
    source = await make_source(session, await make_company(session))
    return await make_posting(
        session, source, title=SAMPLE_JOB_TITLE, description=SAMPLE_JOB_DESCRIPTION, **kwargs
    )


async def extraction_of(session: AsyncSession, snapshot_id: int) -> JobExtraction:
    return (
        await session.execute(
            select(JobExtraction).where(JobExtraction.job_snapshot_id == snapshot_id)
        )
    ).scalar_one()


# --- enqueue ---------------------------------------------------------------------------------------


async def test_the_latest_snapshot_of_each_open_posting_is_queued_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    posting, snapshot = await job(db_session)
    q = queue(db_session, monkeypatch, FakeProvider())
    assert await q.enqueue_missing() == 1
    assert await q.enqueue_missing() == 0  # idempotent
    row = await extraction_of(db_session, snapshot.job_snapshot_id)
    assert (row.status, row.attempts, row.provider, row.model, row.prompt_version) == (
        "pending",
        0,
        "fixture",
        "fixture-model",
        "extract-v1",
    )
    assert posting.closed_at is None


async def test_closed_postings_are_not_queued(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    posting, _snapshot = await job(db_session)
    posting.closed_at = T0
    await db_session.flush()
    assert await queue(db_session, monkeypatch, FakeProvider()).enqueue_missing() == 0


async def test_a_new_model_queues_the_same_snapshot_again(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _posting, snapshot = await job(db_session)
    await queue(db_session, monkeypatch, FakeProvider(model="model-a")).enqueue_missing()
    assert (
        await queue(db_session, monkeypatch, FakeProvider(model="model-b")).enqueue_missing() == 1
    )
    rows = (
        (
            await db_session.execute(
                select(JobExtraction).where(
                    JobExtraction.job_snapshot_id == snapshot.job_snapshot_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert sorted(r.model for r in rows) == ["model-a", "model-b"]


# --- processing ------------------------------------------------------------------------------------


async def test_a_successful_extraction_is_stored_with_skills_and_locations(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _posting, snapshot = await job(db_session)
    provider = FakeProvider([sample_extraction_output()])
    q = queue(db_session, monkeypatch, provider)
    await q.enqueue_missing()
    summary = await q.run_batch()

    assert (summary.succeeded, summary.failed, summary.stopped) == (1, 0, False)
    row = await extraction_of(db_session, snapshot.job_snapshot_id)
    assert (row.status, row.attempts, row.error_class, row.truncated) == (
        "succeeded",
        1,
        None,
        False,
    )
    assert row.latency_ms == 7 and row.completed_at == T0
    stored = row.attributes_json
    assert ExtractionOutput.model_validate(stored["output"]).work_mode.value == "remote"
    assert stored["unverified"] == [] and stored["dropped_keys"] == []
    names = [s["name"] for s in stored["skills_resolved"]]
    assert names == ["Python", "API design"]
    assert all(isinstance(s["skill_id"], int) for s in stored["skills_resolved"])
    skill = await db_session.get(Skill, stored["skills_resolved"][0]["skill_id"])
    assert skill is not None and skill.canonical_name == "Python"
    assert stored["locations_resolved"][0] == {"raw": "Remote - EU", "resolved": False}


async def test_locations_are_resolved_offline_with_coordinates(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _posting, snapshot = await job(db_session)
    answer = sample_extraction_output()
    answer["locations"] = {
        "value": ["Lisbon, Portugal"],
        "status": "known",
        "confidence": 0.9,
        "evidence": "Join our team in Lisbon",
    }
    q = queue(db_session, monkeypatch, FakeProvider([answer]))
    await q.enqueue_missing()
    await q.run_batch()
    stored = (await extraction_of(db_session, snapshot.job_snapshot_id)).attributes_json
    lisbon = stored["locations_resolved"][0]
    assert (lisbon["raw"], lisbon["resolved"], lisbon["country"]) == (
        "Lisbon, Portugal",
        True,
        "PT",
    )
    assert lisbon["timezone"] == "Europe/Lisbon" and abs(lisbon["latitude"] - 38.7) < 0.2


async def test_the_prompt_receives_the_snapshots_title_description_and_hints(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await job(db_session)
    provider = FakeProvider([sample_extraction_output()])
    q = queue(db_session, monkeypatch, provider)
    await q.enqueue_missing()
    await q.run_batch()
    user = provider.requests[0].user
    assert SAMPLE_JOB_TITLE in user and SAMPLE_JOB_DESCRIPTION in user
    assert "Remote" in user  # the snapshot's own location is given as a hint


async def test_an_unavailable_provider_leaves_the_job_waiting_and_stops_the_batch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _p1, first = await job(db_session)
    _p2, second = await job(db_session)
    provider = FakeProvider([ProviderError(ProviderErrorClass.UNAVAILABLE, "down")])
    q = queue(db_session, monkeypatch, provider)
    await q.enqueue_missing()
    summary = await q.run_batch()

    assert (summary.succeeded, summary.failed, summary.stopped) == (0, 0, True)
    assert len(provider.requests) == 1  # it did not hammer the unreachable server
    for snapshot in (first, second):
        row = await extraction_of(db_session, snapshot.job_snapshot_id)
        assert (row.status, row.attempts) == ("pending", 0)
    waiting = [await extraction_of(db_session, s.job_snapshot_id) for s in (first, second)]
    assert {w.error_class for w in waiting} <= {"unavailable", None}
    assert any(w.error_class == "unavailable" for w in waiting)
    assert all(w.claimed_at is None for w in waiting)  # released for the next poll


async def test_timeouts_use_attempts_and_the_third_one_fails_the_extraction(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _p, snapshot = await job(db_session)
    timeout = ProviderError(ProviderErrorClass.TIMEOUT, "slow")
    provider = FakeProvider([timeout, timeout, timeout])
    q = queue(db_session, monkeypatch, provider)
    await q.enqueue_missing()
    for expected_status, expected_attempts in (("pending", 1), ("pending", 2), ("failed", 3)):
        await q.run_batch()
        row = await extraction_of(db_session, snapshot.job_snapshot_id)
        assert (row.status, row.attempts) == (expected_status, expected_attempts)
    assert row.error_class == "timeout" and row.completed_at == T0 and row.attributes_json is None
    summary = await q.run_batch()  # a failed row is final and not picked again
    assert (summary.succeeded, summary.failed) == (0, 0) and len(provider.requests) == 3


async def test_an_unusable_answer_fails_with_invalid_output_after_three_attempts(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _p, snapshot = await job(db_session)
    provider = FakeProvider(responder=lambda _r: "not json at all")
    q = queue(db_session, monkeypatch, provider)
    await q.enqueue_missing()
    for _ in range(3):
        await q.run_batch()
    row = await extraction_of(db_session, snapshot.job_snapshot_id)
    assert (row.status, row.attempts, row.error_class) == ("failed", 3, "invalid_output")
    assert len(provider.requests) == 6  # each attempt: the answer and one repair


async def test_a_claim_is_not_taken_twice_but_a_stale_one_is_recovered(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _p, snapshot = await job(db_session)
    clock = Clock()
    provider = FakeProvider(responder=lambda _r: sample_extraction_output())
    q = queue(db_session, monkeypatch, provider, clock)
    await q.enqueue_missing()
    row = await extraction_of(db_session, snapshot.job_snapshot_id)
    row.claimed_at = clock.now  # another worker holds it
    await db_session.flush()
    assert (await q.run_batch()).succeeded == 0
    clock.now += timedelta(minutes=30)  # that worker died long ago
    assert (await q.run_batch()).succeeded == 1


async def test_the_batch_stops_at_its_time_budget_and_beats_after_each_job(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    for _ in range(3):
        await job(db_session)
    clock = Clock()

    def slow(_request: Any) -> object:
        clock.now += timedelta(seconds=30)
        return sample_extraction_output()

    beats: list[int] = []
    q = queue(db_session, monkeypatch, FakeProvider(responder=slow), clock)
    await q.enqueue_missing()

    async def beat() -> None:
        beats.append(1)

    summary = await q.run_batch(budget_seconds=45, heartbeat=beat)
    assert summary.succeeded == 2  # the third would start after the budget is spent
    assert len(beats) == 2
