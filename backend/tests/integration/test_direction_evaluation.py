"""Evaluations use the stored direction judgements of the profile's enabled directions (ADR-057)."""

from copy import deepcopy
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.data import sample_intent, sample_profile_input
from tests.evaluation_world import World, world

from jobs_radar.db.models import DirectionJudgement, MatchEvaluation
from jobs_radar.domain.directions import direction_hash
from jobs_radar.domain.enums import DIRECTION_PROMPT_VERSION, LOCAL_OWNER_ID
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.profile_api import ProfileInput
from jobs_radar.services.evaluation import EvaluationRecord, EvaluationService
from jobs_radar.services.intents import IntentService
from jobs_radar.services.profiles import ProfileService

pytestmark = pytest.mark.integration

BILLING = "I work as a billing SME and look for telecom roles."
AI = "I am moving from software into AI engineering."


def directions(*items: tuple[str, str, bool]) -> list[dict[str, Any]]:
    return [{"label": label, "text": text, "enabled": on} for label, text, on in items]


async def with_directions(
    session: AsyncSession, w: World, items: list[dict[str, Any]], *, weight: int = 15
) -> tuple[int, int]:
    """Save a profile revision with ``items`` and an intent revision weighing the dimension."""
    profile_input = sample_profile_input()
    profile_input["skills"] = [
        {"name": w.held, "kind": "technology", "level": "expert", "years": 5}
    ]
    saved = await ProfileService(session).save(
        LOCAL_OWNER_ID,
        w.profile_id,
        ProfileInput.model_validate({**profile_input, "directions": items}),
        expected_current_revision=1,
    )
    definition = deepcopy(sample_intent())
    definition["weights"]["career_direction"] = weight
    updated = await IntentService(session).save(
        LOCAL_OWNER_ID,
        w.intent_id,
        IntentDefinition.model_validate(definition),
        expected_current_revision=1,
    )
    assert updated.view.current is not None
    return saved.view.revision.profile_revision_id, updated.view.current.intent_revision_id


def judged(w: World, text: str, level: str, label: str = "Billing SME") -> DirectionJudgement:
    return DirectionJudgement(
        job_snapshot_id=w.snapshot_id,
        direction_hash=direction_hash(text),
        direction_label=label,
        provider="fixture",
        model="m",
        prompt_version=DIRECTION_PROMPT_VERSION,
        level=level,
        job_quote="large enterprises in finance and telecom",
        direction_quote="billing SME",
    )


async def evaluate(
    session: AsyncSession, w: World, profile_id: int, intent_id: int
) -> EvaluationRecord:
    return await EvaluationService(session, provider=None).evaluate(
        LOCAL_OWNER_ID,
        job_snapshot_id=w.snapshot_id,
        job_extraction_id=w.extraction_id,
        profile_revision_id=profile_id,
        intent_revision_id=intent_id,
        judge=False,
    )


def direction_dimension(record: EvaluationRecord) -> Any:
    return next(d for d in record.dimensions if d.dimension_key == "career_direction")


async def test_the_best_stored_judgement_is_scored_and_named(db_session: AsyncSession) -> None:
    w = await world(db_session)
    profile_id, intent_id = await with_directions(
        db_session, w, directions(("Billing SME", BILLING, True), ("AI engineer", AI, True))
    )
    db_session.add_all([judged(w, BILLING, "strong"), judged(w, AI, "weak", "AI engineer")])
    await db_session.flush()
    record = await evaluate(db_session, w, profile_id, intent_id)
    found = direction_dimension(record)
    assert (found.status, found.quality, found.excluded) == ("match", "strong", False)
    assert found.evidence_json["direction"] == "Billing SME"
    assert found.evidence_json["job_quote"] == "large enterprises in finance and telecom"
    assert record.evaluation.direction_basis.startswith("sha256:")
    assert record.evaluation.policy_version == "matching-v1.9"


async def test_a_job_without_judgements_is_not_assessed_and_the_dimension_is_left_out(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    profile_id, intent_id = await with_directions(
        db_session, w, directions(("Billing SME", BILLING, True))
    )
    record = await evaluate(db_session, w, profile_id, intent_id)
    found = direction_dimension(record)
    assert found.excluded is True and found.weight == 0
    assert record.evaluation.direction_basis == "none"


async def test_a_judgement_of_an_edited_text_or_a_disabled_direction_is_ignored(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    profile_id, intent_id = await with_directions(
        db_session, w, directions(("Billing SME", BILLING + " Edited.", True), ("AI", AI, False))
    )
    db_session.add_all([judged(w, BILLING, "strong"), judged(w, AI, "strong", "AI")])
    await db_session.flush()
    record = await evaluate(db_session, w, profile_id, intent_id)
    assert direction_dimension(record).excluded is True
    assert record.evaluation.direction_basis == "none"


async def test_a_late_judgement_gives_a_new_evaluation_and_the_old_one_stays(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    profile_id, intent_id = await with_directions(
        db_session, w, directions(("Billing SME", BILLING, True))
    )
    before = await evaluate(db_session, w, profile_id, intent_id)
    db_session.add(judged(w, BILLING, "strong"))
    await db_session.flush()
    after = await evaluate(db_session, w, profile_id, intent_id)
    again = await evaluate(db_session, w, profile_id, intent_id)
    assert before.evaluation.match_evaluation_id != after.evaluation.match_evaluation_id
    assert after.evaluation.match_evaluation_id == again.evaluation.match_evaluation_id
    assert before.evaluation.direction_basis == "none" != after.evaluation.direction_basis


async def test_a_preview_scores_with_other_weights_and_stores_nothing(
    db_session: AsyncSession,
) -> None:
    w = await world(db_session)
    profile_id, intent_id = await with_directions(
        db_session, w, directions(("Billing SME", BILLING, True)), weight=0
    )
    db_session.add(judged(w, BILLING, "strong"))
    await db_session.flush()
    service = EvaluationService(db_session, provider=None)
    args = {
        "job_snapshot_id": w.snapshot_id,
        "job_extraction_id": w.extraction_id,
        "profile_revision_id": profile_id,
        "intent_revision_id": intent_id,
    }
    plain = await service.preview(LOCAL_OWNER_ID, **args)
    weighted = await service.preview(
        LOCAL_OWNER_ID, **args, weights={"career_direction": 40, "role_responsibilities": 5}
    )
    direction = next(d for d in weighted.dimensions if d.key == "career_direction")
    assert direction.excluded is False and direction.strength == 1
    assert weighted.fit_score != plain.fit_score
    assert weighted.policy_version == "matching-v1.9"
    assert (
        await db_session.execute(
            select(MatchEvaluation).where(MatchEvaluation.job_snapshot_id == w.snapshot_id)
        )
    ).first() is None
