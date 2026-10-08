"""Audited deletion removes personal data through the one allowed bypass and records no content (UC-08)."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import build_full_graph

from jobs_radar.db.models import (
    AuditEvent,
    CareerProfile,
    IntentRevision,
    MatchEvaluation,
    ProfileRevision,
    SearchIntent,
)
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.repositories.deletion import delete_career_profile

pytestmark = pytest.mark.integration


async def count(session: AsyncSession, model: type, **filters: object) -> int:
    statement = select(func.count()).select_from(model)
    for column, value in filters.items():
        statement = statement.where(getattr(model, column) == value)
    return int((await session.execute(statement)).scalar_one())


async def test_plain_deletion_of_a_profile_is_blocked_by_the_triggers(
    db_session: AsyncSession,
) -> None:
    graph = await build_full_graph(db_session)
    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM career_profile WHERE career_profile_id = :i"),
                {"i": graph["profile"].career_profile_id},
            )


async def test_audited_deletion_removes_the_profile_and_everything_derived(
    db_session: AsyncSession,
) -> None:
    graph = await build_full_graph(db_session)
    profile_id = graph["profile"].career_profile_id
    revision_id = graph["profile_revision"].profile_revision_id

    deleted = await delete_career_profile(
        db_session, owner_id=LOCAL_OWNER_ID, career_profile_id=profile_id
    )

    assert deleted["profile_revision"] == 1
    assert deleted["search_intent"] == 1
    assert await count(db_session, CareerProfile, career_profile_id=profile_id) == 0
    assert await count(db_session, ProfileRevision, career_profile_id=profile_id) == 0
    assert await count(db_session, SearchIntent, career_profile_id=profile_id) == 0
    assert (
        await count(db_session, IntentRevision, search_intent_id=graph["intent"].search_intent_id)
        == 0
    )
    # evaluations that used the deleted revisions go with them
    assert await count(db_session, MatchEvaluation, profile_revision_id=revision_id) == 0


async def test_the_audit_event_records_counts_but_no_content(db_session: AsyncSession) -> None:
    graph = await build_full_graph(db_session)
    await delete_career_profile(
        db_session, owner_id=LOCAL_OWNER_ID, career_profile_id=graph["profile"].career_profile_id
    )
    event = (
        (
            await db_session.execute(
                select(AuditEvent)
                .where(AuditEvent.action == "career_profile_deleted")
                .order_by(AuditEvent.audit_event_id.desc())
            )
        )
        .scalars()
        .first()
    )
    assert event is not None
    assert event.owner_id == LOCAL_OWNER_ID
    assert event.subject_type == "career_profile"
    assert event.metadata_json["career_profile_id"] == graph["profile"].career_profile_id
    assert event.metadata_json["deleted_counts"]["profile_revision"] == 1
    serialised = str(event.metadata_json)
    assert "Synthetic profile" not in serialised
    assert "Lisbon" not in serialised  # no profile content


async def test_the_bypass_does_not_leak_into_later_statements(db_session: AsyncSession) -> None:
    graph = await build_full_graph(db_session)
    await delete_career_profile(
        db_session, owner_id=LOCAL_OWNER_ID, career_profile_id=graph["profile"].career_profile_id
    )
    other = await build_full_graph(db_session)
    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM profile_revision WHERE profile_revision_id = :i"),
                {"i": other["profile_revision"].profile_revision_id},
            )


async def test_deleting_someone_elses_or_a_missing_profile_fails(db_session: AsyncSession) -> None:
    from jobs_radar.core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        await delete_career_profile(
            db_session, owner_id=LOCAL_OWNER_ID, career_profile_id=987654321
        )
