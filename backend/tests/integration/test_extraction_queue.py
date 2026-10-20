"""The extraction queue: enqueue, claim, process and finalise (T4.4)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.data import SAMPLE_JOB_DESCRIPTION, SAMPLE_JOB_TITLE, sample_extraction_output
from tests.factories import (
    make_company,
    make_inbox_item,
    make_opportunity,
    make_posting,
    make_source,
    session_factory_for,
    unique,
)
from tests.fake_provider import FakeProvider

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.db.models import JobExtraction, JobPosting, Skill
from jobs_radar.domain.enums import InboxState, ProviderErrorClass
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
        "extract-v4",
    )
    assert posting.closed_at is None


async def test_a_snapshot_with_an_accepted_earlier_extraction_is_not_queued_again(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prompt upgrade does not re-extract jobs already extracted by an accepted version."""
    provider = FakeProvider()
    q = queue(db_session, monkeypatch, provider)
    _, accepted = await job(db_session)
    _, failed_before = await job(db_session)
    _, other_model = await job(db_session)
    taxonomy_id = await q_taxonomy_id(db_session)
    for snapshot, status, model in (
        (accepted, "succeeded", provider.model),
        (failed_before, "failed", provider.model),
        (other_model, "succeeded", "another-model"),
    ):
        db_session.add(
            JobExtraction(
                job_snapshot_id=snapshot.job_snapshot_id,
                status=status,
                provider=provider.provider,
                model=model,
                prompt_version="extract-v2",
                taxonomy_version_id=taxonomy_id,
                attributes_json={} if status == "succeeded" else None,
                attempts=1,
            )
        )
    await db_session.flush()
    assert await q.enqueue_missing() == 2  # only the accepted one is left alone


async def test_a_new_prompt_re_extracts_only_jobs_still_in_the_inbox(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-073: ignored and archived jobs keep their old extraction; open ones and new ones queue."""
    provider = FakeProvider()
    q = queue(db_session, monkeypatch, provider)
    taxonomy_id = await q_taxonomy_id(db_session)
    snapshots = {}
    for name, state in (
        ("unread", InboxState.UNREAD),
        ("ignored", InboxState.IGNORED),
        ("archived", InboxState.ARCHIVED),
        ("fresh", None),  # a new job: no extraction of any version, not yet in the inbox
    ):
        posting, snapshot = await job(db_session)
        snapshots[name] = snapshot
        if name != "fresh":
            item = await make_inbox_item(db_session, await make_opportunity(db_session, posting))
            item.state = state.value  # type: ignore[union-attr]
            db_session.add(
                JobExtraction(
                    job_snapshot_id=snapshot.job_snapshot_id,
                    status="succeeded",
                    provider=provider.provider,
                    model=provider.model,
                    prompt_version="extract-v1",  # neither current nor accepted
                    taxonomy_version_id=taxonomy_id - 1,
                    attributes_json={},
                    attempts=1,
                )
            )
    await db_session.flush()
    assert await q.enqueue_missing() == 2
    queued = {
        name: (
            await db_session.execute(
                select(JobExtraction).where(
                    JobExtraction.job_snapshot_id == snapshot.job_snapshot_id,
                    JobExtraction.status == "pending",
                )
            )
        ).first()
        is not None
        for name, snapshot in snapshots.items()
    }
    assert queued == {"unread": True, "ignored": False, "archived": False, "fresh": True}


async def q_taxonomy_id(session: AsyncSession) -> int:
    from jobs_radar.repositories.extractions import ExtractionRepository

    return await ExtractionRepository(session).current_taxonomy_version_id()


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
    # what was wrong is kept on the row, so the failure can be understood later
    assert row.failure_json["answer_chars"] == len("not json at all")
    assert row.failure_json["answer_tail"] == "not json at all"


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


async def _answered_job_with_score(
    session: AsyncSession, provider: FakeProvider, *, fit: int, recommendation: str
) -> Any:
    """An open job in the inbox that has an old extraction and an evaluation; return its snapshot."""
    from tests.factories import make_evaluation, make_intent, make_profile

    from jobs_radar.domain.enums import Recommendation

    posting, snapshot = await job(session)
    await make_inbox_item(session, await make_opportunity(session, posting))
    old = JobExtraction(
        job_snapshot_id=snapshot.job_snapshot_id,
        status="succeeded",
        provider=provider.provider,
        model=provider.model,
        prompt_version="extract-v1",
        taxonomy_version_id=await q_taxonomy_id(session) - 1,
        attributes_json={},
        attempts=1,
    )
    session.add(old)
    await session.flush()
    profile, profile_revision = await make_profile(session)
    _intent, intent_revision = await make_intent(session, profile)
    await make_evaluation(
        session,
        snapshot,
        old,
        profile_revision,
        intent_revision,
        fit_score=fit,
        recommendation=Recommendation(recommendation),
    )
    return snapshot


async def test_jobs_set_aside_are_not_extracted_again(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner chose to re-extract only what the main inbox shows (ADR-073 amendment)."""
    provider = FakeProvider()
    q = queue(db_session, monkeypatch, provider)
    shown = await _answered_job_with_score(
        db_session, provider, fit=80, recommendation="recommended"
    )
    gated = await _answered_job_with_score(
        db_session, provider, fit=70, recommendation="not_recommended"
    )  # a gate fired
    low = await _answered_job_with_score(db_session, provider, fit=10, recommendation="recommended")
    await q.enqueue_missing()
    ids = [shown.job_snapshot_id, gated.job_snapshot_id, low.job_snapshot_id]
    queued = set(
        (
            await db_session.execute(
                select(JobExtraction.job_snapshot_id).where(
                    JobExtraction.status == "pending", JobExtraction.job_snapshot_id.in_(ids)
                )
            )
        ).scalars()
    )
    assert queued == {shown.job_snapshot_id}  # only the recommended job above the floor


async def test_a_waiting_re_extraction_of_a_set_aside_job_is_not_claimed(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rows queued before the job was set aside stay waiting instead of using model time."""
    from jobs_radar.repositories.extractions import ExtractionRepository

    provider = FakeProvider()
    snapshot = await _answered_job_with_score(
        db_session, provider, fit=70, recommendation="not_recommended"
    )
    db_session.add(
        JobExtraction(
            job_snapshot_id=snapshot.job_snapshot_id,
            status="pending",
            provider=provider.provider,
            model=provider.model,
            prompt_version="extract-v4",
            taxonomy_version_id=await q_taxonomy_id(db_session),
            attempts=0,
        )
    )
    await db_session.flush()
    claimed = await ExtractionRepository(db_session).claim_next(
        provider=provider.provider,
        model=provider.model,
        prompt_version="extract-v4",
        now=T0,
        stale_before=T0 - timedelta(minutes=30),
        set_aside_below=30,
    )
    assert claimed is None


async def test_a_job_never_extracted_is_claimed_before_a_re_extraction(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new job must not wait behind a backlog of re-extractions queued earlier (ADR-073)."""
    from jobs_radar.repositories.extractions import ExtractionRepository

    provider = FakeProvider()
    q = queue(db_session, monkeypatch, provider)
    taxonomy_id = await q_taxonomy_id(db_session)
    _, old = await job(db_session)
    db_session.add(
        JobExtraction(
            job_snapshot_id=old.job_snapshot_id,
            status="succeeded",
            provider=provider.provider,
            model=provider.model,
            prompt_version="extract-v1",
            taxonomy_version_id=taxonomy_id - 1,
            attributes_json={},
            attempts=1,
        )
    )
    await db_session.flush()
    assert await q.enqueue_missing() == 1  # the re-extraction is queued first (lower id)
    _, fresh = await job(db_session)
    assert await q.enqueue_missing() == 1
    claimed = await ExtractionRepository(db_session).claim_next(
        provider=provider.provider,
        model=provider.model,
        prompt_version="extract-v4",
        now=T0,
        stale_before=T0 - timedelta(minutes=30),
    )
    assert claimed is not None
    assert claimed[1].job_snapshot_id == fresh.job_snapshot_id


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


async def test_the_batch_reports_a_backlog_only_when_the_budget_cut_it_short(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    for _ in range(3):
        await job(db_session)
    clock = Clock()

    def slow(_request: Any) -> object:
        clock.now += timedelta(seconds=30)
        return sample_extraction_output()

    q = queue(db_session, monkeypatch, FakeProvider(responder=slow), clock)
    await q.enqueue_missing()

    assert (await q.run_batch(budget_seconds=45)).backlog is True  # one job is still waiting
    assert (await q.run_batch(budget_seconds=45)).backlog is False  # the queue ran dry


# --- concurrency -----------------------------------------------------------------------------------


class _SlowProvider(FakeProvider):
    """A provider that takes time per call and records how many calls overlap."""

    def __init__(self, *, fail: ProviderError | None = None) -> None:
        super().__init__()
        self.fail = fail
        self.in_flight = 0
        self.max_in_flight = 0

    async def extract(self, request: Any) -> Any:
        import asyncio

        from jobs_radar.adapters.providers.base import ProviderOutput

        self.requests.append(request)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0.05)
            if self.fail is not None:
                raise self.fail
            import json

            return ProviderOutput(content=json.dumps(sample_extraction_output()), latency_ms=7)
        finally:
            self.in_flight -= 1


async def test_with_concurrency_several_jobs_are_sent_to_the_model_at_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshots = [(await job(db_session))[1] for _ in range(5)]
    provider = _SlowProvider()
    q = queue(db_session, monkeypatch, provider, concurrency=3)
    await q.enqueue_missing()

    summary = await q.run_batch()

    assert provider.max_in_flight == 3
    assert (summary.succeeded, summary.failed, summary.backlog) == (5, 0, False)
    for snapshot in snapshots:  # every job was extracted exactly once
        assert (await extraction_of(db_session, snapshot.job_snapshot_id)).status == "succeeded"
    assert len(provider.requests) == 5


async def test_by_default_jobs_go_to_the_model_one_at_a_time(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    for _ in range(3):
        await job(db_session)
    provider = _SlowProvider()
    q = queue(db_session, monkeypatch, provider)
    await q.enqueue_missing()

    assert (await q.run_batch()).succeeded == 3
    assert provider.max_in_flight == 1


async def test_a_model_that_is_down_ends_the_whole_concurrent_batch_and_loses_no_job(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshots = [(await job(db_session))[1] for _ in range(6)]
    provider = _SlowProvider(fail=ProviderError(ProviderErrorClass.UNAVAILABLE, "down"))
    q = queue(db_session, monkeypatch, provider, concurrency=3)
    await q.enqueue_missing()

    summary = await q.run_batch()

    assert summary.stopped is True
    assert len(provider.requests) <= 3  # nothing new is claimed once the model is known to be down
    for snapshot in snapshots:  # all rows wait, unclaimed and with no attempt used
        row = await extraction_of(db_session, snapshot.job_snapshot_id)
        assert (row.status, row.attempts, row.claimed_at) == ("pending", 0, None)


async def test_the_time_budget_still_ends_a_concurrent_batch_with_a_backlog(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    for _ in range(6):
        await job(db_session)
    clock = Clock()

    def slow(_request: Any) -> object:
        clock.now += timedelta(seconds=30)
        return sample_extraction_output()

    q = queue(db_session, monkeypatch, FakeProvider(responder=slow), clock, concurrency=2)
    await q.enqueue_missing()

    summary = await q.run_batch(budget_seconds=45)

    assert summary.backlog is True
    assert 0 < summary.succeeded < 6


# --- no re-extraction of jobs already extracted ---------------------------------------------------


async def _answer(
    session: AsyncSession, snapshot: Any, *, prompt: str, taxonomy_offset: int = 0, **fields: Any
) -> JobExtraction:
    """Store a finished or waiting extraction by the fake provider for ``snapshot``."""
    provider = FakeProvider()
    row = JobExtraction(
        job_snapshot_id=snapshot.job_snapshot_id,
        provider=provider.provider,
        model=provider.model,
        prompt_version=prompt,
        taxonomy_version_id=await q_taxonomy_id(session) - taxonomy_offset,
        **fields,
    )
    session.add(row)
    await session.flush()
    return row


async def test_a_new_taxonomy_version_does_not_re_extract_jobs_with_an_accepted_answer(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, snapshot = await job(db_session)
    await _answer(
        db_session,
        snapshot,
        prompt="extract-v2",
        taxonomy_offset=1,  # an older taxonomy than the current one
        status="succeeded",
        attributes_json={},
        attempts=1,
    )
    q = queue(db_session, monkeypatch, FakeProvider())
    assert await q.enqueue_missing() == 0


async def test_a_waiting_row_of_a_job_with_an_accepted_answer_is_never_sent_to_the_model(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rows queued before the rule existed must not spend model time either."""
    _, answered = await job(db_session)
    _, fresh = await job(db_session)
    await _answer(
        db_session,
        answered,
        prompt="extract-v2",
        taxonomy_offset=1,
        status="succeeded",
        attributes_json={},
        attempts=1,
    )
    stale = await _answer(db_session, answered, prompt="extract-v4", status="pending")
    provider = FakeProvider([sample_extraction_output()])
    q = queue(db_session, monkeypatch, provider)
    assert await q.enqueue_missing() == 1  # only the fresh job

    summary = await q.run_batch()

    assert (summary.succeeded, len(provider.requests)) == (1, 1)
    assert (await extraction_of(db_session, fresh.job_snapshot_id)).status == "succeeded"
    await db_session.refresh(stale)
    assert (stale.status, stale.claimed_at) == ("pending", None)
    assert summary.backlog is False  # the skipped row is not a backlog


async def test_the_model_is_offered_active_terms_only(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-080: a role family the owner switched off is not in the allowed keys of the prompt."""
    from jobs_radar.services.taxonomy import TaxonomyService

    service = TaxonomyService(db_session)
    kept = await service.add("role_family", unique("Kept family"))
    dropped = await service.add("role_family", unique("Dropped family"))
    await service.update("role_family", dropped.term_key, active=False)
    await job(db_session)
    provider = FakeProvider(responder=lambda _request: {})
    q = queue(db_session, monkeypatch, provider)
    await q.enqueue_missing()
    await q.run_batch()
    assert provider.requests, "the job was not sent to the model"
    prompt = provider.requests[0].user
    assert kept.term_key in prompt and dropped.term_key not in prompt
