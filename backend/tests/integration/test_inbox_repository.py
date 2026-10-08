"""Inbox items and their append-only events (LLD sections 3 and 7, ADR-006)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import build_full_graph, make_opportunity, make_posting

from jobs_radar.core.errors import ConflictError, NotFoundError
from jobs_radar.db.models import InboxEvent
from jobs_radar.domain.enums import LOCAL_OWNER_ID, Actor, InboxAction, InboxState
from jobs_radar.repositories.inbox import InboxRepository

pytestmark = pytest.mark.integration


async def events_of(session: AsyncSession, item_id: int) -> list[InboxEvent]:
    result = await session.execute(
        select(InboxEvent)
        .where(InboxEvent.job_inbox_item_id == item_id)
        .order_by(InboxEvent.inbox_event_id)
    )
    return list(result.scalars())


async def fresh_opportunity(session: AsyncSession):  # type: ignore[no-untyped-def]
    graph = await build_full_graph(session)
    posting, _ = await make_posting(session, graph["source"])
    return await make_opportunity(session, posting)


async def test_surfacing_a_new_opportunity_creates_an_unread_item_and_one_event(
    db_session: AsyncSession,
) -> None:
    opportunity = await fresh_opportunity(db_session)
    repository = InboxRepository(db_session)
    item = await repository.surface(LOCAL_OWNER_ID, opportunity.job_opportunity_id)
    assert item.state == InboxState.UNREAD.value
    assert item.is_shortlisted is False
    assert item.version == 1
    events = await events_of(db_session, item.job_inbox_item_id)
    assert [(e.action, e.actor, e.from_state, e.to_state) for e in events] == [
        (InboxAction.SURFACE_NEW.value, Actor.SYSTEM.value, None, InboxState.UNREAD.value)
    ]


async def test_surfacing_twice_returns_the_same_item(db_session: AsyncSession) -> None:
    opportunity = await fresh_opportunity(db_session)
    repository = InboxRepository(db_session)
    first = await repository.surface(LOCAL_OWNER_ID, opportunity.job_opportunity_id)
    second = await repository.surface(LOCAL_OWNER_ID, opportunity.job_opportunity_id)
    assert second.job_inbox_item_id == first.job_inbox_item_id
    assert len(await events_of(db_session, first.job_inbox_item_id)) == 1  # no duplicate event


async def test_a_transition_updates_state_and_version_and_appends_an_event(
    db_session: AsyncSession,
) -> None:
    opportunity = await fresh_opportunity(db_session)
    repository = InboxRepository(db_session)
    item = await repository.surface(LOCAL_OWNER_ID, opportunity.job_opportunity_id)

    event = await repository.apply(
        item,
        expected_version=1,
        action=InboxAction.IGNORE,
        to_state=InboxState.IGNORED,
        actor=Actor.USER,
        changes={"ignore_reason": "wrong_contract", "note": "Employee-only role."},
        metadata={"reason": "wrong_contract"},
    )
    assert item.state == "ignored"
    assert item.version == 2
    assert item.ignore_reason == "wrong_contract"
    assert item.note == "Employee-only role."
    assert (event.from_state, event.to_state, event.actor) == ("unread", "ignored", "user")
    assert len(await events_of(db_session, item.job_inbox_item_id)) == 2


async def test_a_stale_version_is_a_conflict_that_changes_nothing(db_session: AsyncSession) -> None:
    opportunity = await fresh_opportunity(db_session)
    repository = InboxRepository(db_session)
    item = await repository.surface(LOCAL_OWNER_ID, opportunity.job_opportunity_id)
    await repository.apply(
        item,
        expected_version=1,
        action=InboxAction.OPEN,
        to_state=InboxState.READ,
        actor=Actor.USER,
    )

    with pytest.raises(ConflictError) as error:
        await repository.apply(
            item,
            expected_version=1,
            action=InboxAction.ARCHIVE,
            to_state=InboxState.ARCHIVED,
            actor=Actor.USER,
        )
    assert error.value.details == {"expected": 1, "actual": 2}
    assert item.state == "read"
    assert len(await events_of(db_session, item.job_inbox_item_id)) == 2  # surface + open


async def test_the_shortlist_flag_is_independent_of_the_state(db_session: AsyncSession) -> None:
    opportunity = await fresh_opportunity(db_session)
    repository = InboxRepository(db_session)
    item = await repository.surface(LOCAL_OWNER_ID, opportunity.job_opportunity_id)
    await repository.apply(
        item,
        expected_version=1,
        action=InboxAction.SHORTLIST,
        to_state=InboxState.UNREAD,
        actor=Actor.USER,
        changes={"is_shortlisted": True},
    )
    assert item.is_shortlisted is True
    assert item.state == "unread"


async def test_only_whitelisted_columns_can_be_changed(db_session: AsyncSession) -> None:
    opportunity = await fresh_opportunity(db_session)
    repository = InboxRepository(db_session)
    item = await repository.surface(LOCAL_OWNER_ID, opportunity.job_opportunity_id)
    with pytest.raises(ValueError, match="owner_id"):
        await repository.apply(
            item,
            expected_version=1,
            action=InboxAction.OPEN,
            to_state=InboxState.READ,
            actor=Actor.USER,
            changes={"owner_id": 5},
        )


async def test_items_are_scoped_to_their_owner(db_session: AsyncSession) -> None:
    opportunity = await fresh_opportunity(db_session)
    repository = InboxRepository(db_session)
    item = await repository.surface(LOCAL_OWNER_ID, opportunity.job_opportunity_id)
    assert (
        await repository.get(LOCAL_OWNER_ID, item.job_inbox_item_id)
    ).job_inbox_item_id == item.job_inbox_item_id
    with pytest.raises(NotFoundError):
        await repository.get(owner_id=999, job_inbox_item_id=item.job_inbox_item_id)
    with pytest.raises(NotFoundError):
        await repository.get(LOCAL_OWNER_ID, 987654321)
