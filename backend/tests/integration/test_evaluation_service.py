"""Persisting evaluations, judging skill pairs and re-scoring without AI (T4.6)."""

from copy import deepcopy
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.data import (
    sample_intent,
)
from tests.evaluation_world import NOW, world
from tests.factories import unique
from tests.fake_provider import FakeProvider

from jobs_radar.core.errors import ConflictError, NotFoundError
from jobs_radar.db.models import (
    JobExtraction,
    MatchEvaluation,
    ScoreDimension,
)
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.services.evaluation import EvaluationRunner, EvaluationService
from jobs_radar.services.intents import IntentService

pytestmark = pytest.mark.integration


async def count(session: AsyncSession, model: type, **filters: Any) -> int:
    statement = select(func.count()).select_from(model)
    for column, value in filters.items():
        statement = statement.where(getattr(model, column) == value)
    return int((await session.execute(statement)).scalar_one())


def pair_judgement(held_name: str, unheld_name: str):  # type: ignore[no-untyped-def]
    return lambda request: {"equivalent": [held_name], "related": [], "unrelated": []}


# --- evaluating one snapshot -----------------------------------------------------------------------------


async def test_an_evaluation_is_persisted_with_every_input_and_all_dimensions(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    service = EvaluationService(db_session, provider=None)
    record = await service.evaluate(
        LOCAL_OWNER_ID,
        job_snapshot_id=w.snapshot_id,
        job_extraction_id=w.extraction_id,
        profile_revision_id=w.profile_revision_id,
        intent_revision_id=w.intent_revision_id,
        judge=False,
    )
    evaluation = record.evaluation
    assert (evaluation.job_snapshot_id, evaluation.job_extraction_id) == (
        w.snapshot_id,
        w.extraction_id,
    )
    assert (evaluation.profile_revision_id, evaluation.intent_revision_id) == (
        w.profile_revision_id,
        w.intent_revision_id,
    )
    assert evaluation.policy_version == "matching-v1.7"
    assert evaluation.job_source_hash.startswith("sha256:")
    assert 0 <= evaluation.fit_score <= 100 and evaluation.recommendation in {
        "recommended",
        "not_recommended",
    }
    assert evaluation.weights_json["role_responsibilities"] == 25
    assert len(record.dimensions) == 11
    assert (
        await count(db_session, ScoreDimension, match_evaluation_id=evaluation.match_evaluation_id)
        == 11
    )
    by_key = {d.dimension_key: d for d in record.dimensions}
    assert (
        by_key["work_arrangement_location"].status == "match"
    )  # remote within EU, remote preferred
    assert by_key["qualifications"].excluded is True
    assert by_key["compensation"].status == "unknown" and by_key["compensation"].strength == 0


async def test_a_source_place_limited_to_another_country_stops_a_remote_job_from_matching(
    db_session: AsyncSession,
) -> None:
    # The model reported EU, but the board's own location says the job is remote in India (ADR-056).
    w = await world(db_session, locations=["India (Remote)"])
    record = await EvaluationService(db_session, provider=None).evaluate(
        LOCAL_OWNER_ID,
        job_snapshot_id=w.snapshot_id,
        job_extraction_id=w.extraction_id,
        profile_revision_id=w.profile_revision_id,
        intent_revision_id=w.intent_revision_id,
        judge=False,
    )
    assert record.evaluation.recommendation == "not_recommended"
    assert any(gate["code"] == "G2" for gate in record.evaluation.gates_json)
    by_key = {d.dimension_key: d for d in record.dimensions}
    assert by_key["work_arrangement_location"].status == "mismatch"


async def test_evaluating_twice_returns_the_same_evaluation(db_session: AsyncSession) -> None:
    w = await world(db_session)
    service = EvaluationService(db_session, provider=None)
    args: dict[str, Any] = {
        "job_snapshot_id": w.snapshot_id,
        "job_extraction_id": w.extraction_id,
        "profile_revision_id": w.profile_revision_id,
        "intent_revision_id": w.intent_revision_id,
        "judge": False,
    }
    first = await service.evaluate(LOCAL_OWNER_ID, **args)
    second = await service.evaluate(LOCAL_OWNER_ID, **args)
    assert first.evaluation.match_evaluation_id == second.evaluation.match_evaluation_id
    assert await count(db_session, MatchEvaluation, job_snapshot_id=w.snapshot_id) == 1


async def test_a_failed_extraction_cannot_be_evaluated(db_session: AsyncSession) -> None:
    w = await world(db_session)
    extraction = await db_session.get(JobExtraction, w.extraction_id)
    assert extraction is not None
    pending = JobExtraction(
        job_snapshot_id=w.snapshot_id,
        status="pending",
        provider="p",
        model=unique("m"),
        prompt_version="extract-v2",
        taxonomy_version_id=1,
    )
    db_session.add(pending)
    await db_session.flush()
    with pytest.raises(ConflictError, match="extract"):
        await EvaluationService(db_session, None).evaluate(
            LOCAL_OWNER_ID,
            job_snapshot_id=w.snapshot_id,
            job_extraction_id=pending.job_extraction_id,
            profile_revision_id=w.profile_revision_id,
            intent_revision_id=w.intent_revision_id,
            judge=False,
        )


async def test_revisions_of_another_owner_or_unknown_ones_are_not_found(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    with pytest.raises(NotFoundError):
        await EvaluationService(db_session, None).evaluate(
            LOCAL_OWNER_ID,
            job_snapshot_id=w.snapshot_id,
            job_extraction_id=w.extraction_id,
            profile_revision_id=987654321,
            intent_revision_id=w.intent_revision_id,
            judge=False,
        )


# --- skill pairs -------------------------------------------------------------------------------------------


async def test_without_a_provider_unmatched_skills_stay_unjudged(db_session: AsyncSession) -> None:
    w = await world(db_session)
    record = await EvaluationService(db_session, None).evaluate(
        LOCAL_OWNER_ID,
        job_snapshot_id=w.snapshot_id,
        job_extraction_id=w.extraction_id,
        profile_revision_id=w.profile_revision_id,
        intent_revision_id=w.intent_revision_id,
        judge=True,
    )
    skills = {d.dimension_key: d for d in record.dimensions}["skills_technology"]
    assert float(skills.strength) == 0.5  # one must held (2) + one must missing (2): 2/4


async def test_pairs_are_judged_once_and_a_later_evaluation_uses_the_cache(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    provider = FakeProvider(
        responder=lambda _r: {"equivalent": [w.held], "related": [], "unrelated": []}
    )
    service = EvaluationService(db_session, provider)
    first = await service.evaluate(
        LOCAL_OWNER_ID,
        job_snapshot_id=w.snapshot_id,
        job_extraction_id=w.extraction_id,
        profile_revision_id=w.profile_revision_id,
        intent_revision_id=w.intent_revision_id,
        judge=True,
    )
    assert len(provider.requests) == 1
    assert w.unheld in provider.requests[0].user
    skills = {d.dimension_key: d for d in first.dimensions}["skills_technology"]
    assert (
        float(skills.strength) == 0.75
    )  # held 1.0 and the other equivalent to it 0.5: (2 + 1) / 4

    # a new intent revision (heavier compensation weight) re-scores from the stored extraction and
    # the cached judgement: no further model call
    changed = deepcopy(sample_intent())
    changed["weights"]["compensation"] = 30
    saved = await IntentService(db_session).save(
        LOCAL_OWNER_ID,
        w.intent_id,
        IntentDefinition.model_validate(changed),
        expected_current_revision=1,
    )
    assert saved.view.current is not None
    second = await service.evaluate(
        LOCAL_OWNER_ID,
        job_snapshot_id=w.snapshot_id,
        job_extraction_id=w.extraction_id,
        profile_revision_id=w.profile_revision_id,
        intent_revision_id=saved.view.current.intent_revision_id,
        judge=True,
    )
    assert second.evaluation.match_evaluation_id != first.evaluation.match_evaluation_id
    assert len(provider.requests) == 1
    assert second.evaluation.weights_json["compensation"] == 30
    assert (
        await count(db_session, MatchEvaluation, job_snapshot_id=w.snapshot_id) == 2
    )  # history kept


# --- pending work and re-scoring ----------------------------------------------------------------------------


async def test_pending_evaluations_cover_jobs_not_yet_scored_for_an_enabled_intent(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    service = EvaluationService(db_session, None)
    assert await service.evaluate_pending(intent_id=w.intent_id) == 1
    assert await service.evaluate_pending(intent_id=w.intent_id) == 0  # nothing left


async def test_a_disabled_intent_is_not_evaluated(db_session: AsyncSession) -> None:
    w = await world(db_session)
    intents = IntentService(db_session)
    view = await intents.get(LOCAL_OWNER_ID, w.intent_id)
    await intents.set_enabled(
        LOCAL_OWNER_ID, w.intent_id, enabled=False, expected_version=view.intent.version
    )
    assert await EvaluationService(db_session, None).evaluate_pending(intent_id=w.intent_id) == 0


async def test_a_new_intent_revision_does_not_rescore_old_jobs_by_itself(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    service = EvaluationService(db_session, None)
    await service.evaluate_pending(intent_id=w.intent_id)
    changed = deepcopy(sample_intent())
    changed["weights"]["compensation"] = 30
    await IntentService(db_session).save(
        LOCAL_OWNER_ID,
        w.intent_id,
        IntentDefinition.model_validate(changed),
        expected_current_revision=1,
    )
    assert (
        await service.evaluate_pending(intent_id=w.intent_id) == 0
    )  # "new weights apply from now on"
    assert await count(db_session, MatchEvaluation, job_snapshot_id=w.snapshot_id) == 1


async def test_rescoring_evaluates_existing_jobs_under_the_current_revision_with_no_ai(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    provider = FakeProvider(
        responder=lambda _r: {"equivalent": [], "related": [], "unrelated": [w.held]}
    )
    first = EvaluationService(db_session, provider)
    await first.evaluate_pending(intent_id=w.intent_id)
    calls = len(provider.requests)

    changed = deepcopy(sample_intent())
    changed["weights"]["compensation"] = 30
    await IntentService(db_session).save(
        LOCAL_OWNER_ID,
        w.intent_id,
        IntentDefinition.model_validate(changed),
        expected_current_revision=1,
    )
    summary = await EvaluationService(db_session, None).rescore(LOCAL_OWNER_ID, w.intent_id)
    assert (summary.evaluated, summary.skipped) == (1, 0)
    assert len(provider.requests) == calls  # the rescoring had no provider at all
    evaluations = (
        (
            await db_session.execute(
                select(MatchEvaluation)
                .where(MatchEvaluation.job_snapshot_id == w.snapshot_id)
                .order_by(MatchEvaluation.match_evaluation_id)
            )
        )
        .scalars()
        .all()
    )
    assert [e.weights_json["compensation"] for e in evaluations] == [10, 30]
    again = await EvaluationService(db_session, None).rescore(LOCAL_OWNER_ID, w.intent_id)
    assert (again.evaluated, again.skipped) == (0, 1)  # already scored under this revision


async def test_rescoring_also_covers_jobs_scored_under_an_earlier_policy(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a policy change (ADR-058) a rescore scores every job again, with no model call."""
    w = await world(db_session)
    await EvaluationService(db_session, None).evaluate_pending(intent_id=w.intent_id)
    # The stored evaluation carries the old policy; the running code now has a newer one.
    monkeypatch.setattr("jobs_radar.services.evaluation.POLICY_VERSION", "matching-v9.9")
    summary = await EvaluationService(db_session, None).rescore(LOCAL_OWNER_ID, w.intent_id)
    assert summary.evaluated == 1


async def test_a_materially_changed_job_gets_a_new_evaluation_for_its_new_snapshot(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    service = EvaluationService(db_session, None)
    await service.evaluate_pending(intent_id=w.intent_id)
    # a second snapshot of the same posting with its own extraction
    from tests.factories import NOW as FACTORY_NOW  # noqa: F401

    from jobs_radar.db.models import JobSnapshot

    new_snapshot = JobSnapshot(
        job_posting_id=w.posting.job_posting_id,
        content_hash="sha256:" + "b" * 64,
        fetched_at=NOW,
        raw_payload_json={},
        normalised_json=(await db_session.get(JobSnapshot, w.snapshot_id)).normalised_json,  # type: ignore[union-attr]
    )
    db_session.add(new_snapshot)
    await db_session.flush()
    old = await db_session.get(JobExtraction, w.extraction_id)
    assert old is not None
    db_session.add(
        JobExtraction(
            job_snapshot_id=new_snapshot.job_snapshot_id,
            status="succeeded",
            provider="fixture",
            model=unique("m"),
            prompt_version="extract-v2",
            taxonomy_version_id=1,
            attributes_json=old.attributes_json,
            attempts=1,
            completed_at=NOW,
        )
    )
    await db_session.flush()
    assert await service.evaluate_pending(intent_id=w.intent_id) == 1
    assert (
        await count(db_session, MatchEvaluation, job_snapshot_id=new_snapshot.job_snapshot_id) == 1
    )


async def test_get_returns_a_persisted_evaluation_and_hides_other_owners(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    service = EvaluationService(db_session, None)
    await service.evaluate_pending(intent_id=w.intent_id)
    evaluation = (
        await db_session.execute(
            select(MatchEvaluation).where(MatchEvaluation.job_snapshot_id == w.snapshot_id)
        )
    ).scalar_one()
    record = await service.get(LOCAL_OWNER_ID, evaluation.match_evaluation_id)
    assert len(record.dimensions) == 11
    with pytest.raises(NotFoundError):
        await service.get(LOCAL_OWNER_ID, 987654321)


async def test_places_are_resolved_when_scoring_so_the_sources_own_locations_count(
    db_session: AsyncSession,
) -> None:
    """The extraction cannot quote a job's location (it lives in the board's metadata), so the
    source's own places are split and resolved at scoring time, with the offline gazetteer."""
    from jobs_radar.db.models import JobSnapshot

    w = await world(db_session)
    extraction = await db_session.get(JobExtraction, w.extraction_id)
    snapshot = await db_session.get(JobSnapshot, w.snapshot_id)
    assert extraction is not None and snapshot is not None
    output = extraction.attributes_json["output"]
    output["work_mode"] = {
        "value": "hybrid",
        "status": "known",
        "confidence": 0.9,
        "evidence": "Hybrid",
    }
    output["locations"] = {"value": None, "status": "unknown", "confidence": 0.0, "evidence": None}
    snapshot.normalised_json["work_arrangement"]["locations"] = [
        {"raw": "Berlin, Germany; Setúbal, Portugal"}
    ]
    # the stored (older) resolution knew nothing about these places
    extraction.attributes_json["locations_resolved"] = [
        {"raw": "Berlin, Germany; Setúbal, Portugal", "resolved": False}
    ]
    await db_session.flush()

    record = await EvaluationService(db_session, None).evaluate(
        LOCAL_OWNER_ID,
        job_snapshot_id=w.snapshot_id,
        job_extraction_id=w.extraction_id,
        profile_revision_id=w.profile_revision_id,
        intent_revision_id=w.intent_revision_id,
        judge=False,
    )
    work = {d.dimension_key: d for d in record.dimensions}["work_arrangement_location"]
    assert work.status == "match"  # Setúbal is within 40 km of the base place
    kms = {item["place"]: item["km"] for item in work.evidence_json["locations"]}
    assert kms["Setúbal, Portugal"] < 40 and kms["Berlin, Germany"] > 1000


# --- the worker's runner: one short transaction per job, heartbeat, time budget -------------------------------


async def test_the_runner_commits_each_job_and_beats_the_heartbeat_between_jobs(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A long scoring pass must keep the worker alive and save progress job by job."""
    from tests.factories import session_factory_for

    provider = FakeProvider(responder=lambda _request: {"equivalent": [], "related": []})
    w = await world(db_session, extracted_by=(provider.provider, provider.model))
    factory = session_factory_for(db_session, monkeypatch)
    commits: list[int] = []
    monkeypatch.setattr(db_session, "commit", lambda: _record(commits, db_session))
    beats: list[int] = []

    async def beat() -> None:
        beats.append(1)

    scored = await EvaluationRunner(factory, provider).run(heartbeat=beat)

    assert scored == 1
    assert len(beats) >= 1
    assert len(commits) >= 1
    assert await count(db_session, MatchEvaluation, job_snapshot_id=w.snapshot_id) == 1


async def _record(commits: list[int], session: AsyncSession) -> None:
    commits.append(1)
    await session.flush()


async def test_the_runner_stops_when_its_time_budget_is_spent(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no time left nothing is scored, and the job stays waiting for the next iteration."""
    from tests.factories import session_factory_for

    provider = FakeProvider(responder=lambda _request: {"equivalent": [], "related": []})
    w = await world(db_session, extracted_by=(provider.provider, provider.model))
    factory = session_factory_for(db_session, monkeypatch)

    scored = await EvaluationRunner(factory, provider).run(budget_seconds=0)

    assert scored == 0
    assert await count(db_session, MatchEvaluation, job_snapshot_id=w.snapshot_id) == 0
