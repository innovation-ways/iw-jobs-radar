"""Inbox use cases: surfacing, actions, filters, sorting, detail and material updates (T4.8)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import (
    make_company,
    make_opportunity,
    make_posting,
    make_source,
)
from tests.inbox_scene import T0, Entry, Scene, scene

from jobs_radar.core.errors import ConflictError, InputValidationError, NotFoundError
from jobs_radar.db.models import (
    Company,
    InboxEvent,
    IntentRevision,
    JobExtraction,
    JobInboxItem,
    ProfileRevision,
    SearchIntent,
)
from jobs_radar.domain.enums import (
    LOCAL_OWNER_ID,
    InboxAction,
    InboxState,
    Recommendation,
    SourceType,
)
from jobs_radar.services.inbox import InboxService

pytestmark = pytest.mark.integration

A = InboxAction


# --- surfacing -----------------------------------------------------------------------------------------------


async def test_every_open_opportunity_without_an_item_gets_one_with_a_surface_event(
    db_session: AsyncSession,
) -> None:
    source = await make_source(db_session, await make_company(db_session))
    posting, _s = await make_posting(db_session, source)
    opportunity = await make_opportunity(db_session, posting)
    closed_posting, _s2 = await make_posting(db_session, source)
    closed = await make_opportunity(db_session, closed_posting)
    closed.closed_at = T0
    await db_session.flush()

    service = InboxService(db_session)
    assert await service.surface_new(LOCAL_OWNER_ID) >= 1
    item = (
        await db_session.execute(
            select(JobInboxItem).where(
                JobInboxItem.job_opportunity_id == opportunity.job_opportunity_id
            )
        )
    ).scalar_one()
    assert item.state == "unread" and item.version == 1
    events = (
        (
            await db_session.execute(
                select(InboxEvent).where(InboxEvent.job_inbox_item_id == item.job_inbox_item_id)
            )
        )
        .scalars()
        .all()
    )
    assert [e.action for e in events] == ["surface_new"]
    none_for_closed = await db_session.scalar(
        select(func.count())
        .select_from(JobInboxItem)
        .where(JobInboxItem.job_opportunity_id == closed.job_opportunity_id)
    )
    assert none_for_closed == 0
    assert await service.surface_new(LOCAL_OWNER_ID) == 0  # idempotent


# --- actions -----------------------------------------------------------------------------------------------------


async def act(session: AsyncSession, entry: Entry, action: InboxAction, **kwargs: Any):  # type: ignore[no-untyped-def]
    await session.refresh(entry.item)
    return await InboxService(session).act(
        LOCAL_OWNER_ID,
        entry.item.job_inbox_item_id,
        action,
        expected_version=entry.item.version,
        **kwargs,
    )


async def test_opening_marks_the_item_read_records_the_time_and_appends_an_event(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    entry = await s.entry()
    result = await act(db_session, entry, A.OPEN)
    assert (result.item.state, result.item.version) == ("read", 2)
    assert result.item.read_at is not None
    assert (
        result.event.action,
        result.event.from_state,
        result.event.to_state,
        result.event.actor,
    ) == ("open", "unread", "read", "user")


async def test_opening_an_item_that_is_already_read_changes_nothing(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    entry = await s.entry(state=InboxState.READ)
    result = await act(db_session, entry, A.OPEN)
    assert result.event is None and result.item.version == 1


async def test_ignoring_keeps_the_reason_and_note_in_the_item_and_the_event(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    entry = await s.entry()
    result = await act(
        db_session, entry, A.IGNORE, reason="wrong_contract", note="Employee-only role."
    )
    assert result.item.state == "ignored"
    assert (result.item.ignore_reason, result.item.note) == (
        "wrong_contract",
        "Employee-only role.",
    )
    assert result.event is not None and result.event.metadata_json == {
        "reason": "wrong_contract"
    }  # no free text in events


async def test_restoring_returns_to_read_and_marking_unread_returns_to_unread(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    entry = await s.entry()
    await act(db_session, entry, A.IGNORE)
    assert (await act(db_session, entry, A.RESTORE)).item.state == "read"
    assert (await act(db_session, entry, A.MARK_UNREAD)).item.state == "unread"


async def test_shortlisting_is_independent_of_the_state(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    entry = await s.entry(state=InboxState.READ)
    shortlisted = await act(db_session, entry, A.SHORTLIST)
    assert (shortlisted.item.state, shortlisted.item.is_shortlisted) == ("read", True)
    assert (
        shortlisted.event is not None
        and shortlisted.event.from_state == shortlisted.event.to_state == "read"
    )
    ignored = await act(db_session, entry, A.IGNORE)
    assert (ignored.item.state, ignored.item.is_shortlisted) == (
        "ignored",
        True,
    )  # still shortlisted
    assert (await act(db_session, entry, A.UNSHORTLIST)).item.is_shortlisted is False


async def test_shortlisting_twice_or_unshortlisting_an_unmarked_item_is_invalid(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    entry = await s.entry()
    with pytest.raises(InputValidationError):
        await act(db_session, entry, A.UNSHORTLIST)
    await act(db_session, entry, A.SHORTLIST)
    with pytest.raises(InputValidationError):
        await act(db_session, entry, A.SHORTLIST)


async def test_recording_an_application_stores_the_details_and_restore_undoes_it(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    entry = await s.entry(state=InboxState.READ)
    applied_at = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    result = await act(
        db_session,
        entry,
        A.RECORD_APPLICATION,
        applied_at=applied_at,
        application_url="https://careers.example.test/apply/1",
        note="Sent CV.",
    )
    assert result.item.state == "applied"
    assert result.item.applied_at == applied_at
    assert result.item.application_url == "https://careers.example.test/apply/1"
    undone = await act(db_session, entry, A.RESTORE)
    assert (undone.item.state, undone.item.applied_at, undone.item.application_url) == (
        "read",
        None,
        None,
    )


async def test_an_application_without_a_date_uses_the_current_time(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    entry = await s.entry()
    result = await act(db_session, entry, A.RECORD_APPLICATION)
    assert result.item.applied_at is not None


@pytest.mark.parametrize(
    ("state", "action"),
    [
        (InboxState.APPLIED, A.IGNORE),
        (InboxState.ARCHIVED, A.OPEN),
        (InboxState.IGNORED, A.RECORD_APPLICATION),
        (InboxState.UNREAD, A.RESTORE),
        (InboxState.UNREAD, A.MARK_UNREAD),
    ],
)
async def test_invalid_transitions_are_refused_without_changing_anything(
    db_session: AsyncSession, state: InboxState, action: InboxAction
) -> None:
    s = await scene(db_session)
    entry = await s.entry(state=state)
    with pytest.raises(InputValidationError, match="not allowed"):
        await act(db_session, entry, action)
    await db_session.refresh(entry.item)
    assert (entry.item.state, entry.item.version) == (state.value, 1)
    events = await db_session.scalar(
        select(func.count())
        .select_from(InboxEvent)
        .where(InboxEvent.job_inbox_item_id == entry.item.job_inbox_item_id)
    )
    assert events == 0


async def test_a_stale_version_is_a_conflict_and_changes_nothing(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    entry = await s.entry()
    await act(db_session, entry, A.OPEN)
    with pytest.raises(ConflictError):
        await InboxService(db_session).act(
            LOCAL_OWNER_ID, entry.item.job_inbox_item_id, A.IGNORE, expected_version=1
        )


async def test_unknown_items_are_not_found(db_session: AsyncSession) -> None:
    with pytest.raises(NotFoundError):
        await InboxService(db_session).act(LOCAL_OWNER_ID, 987654321, A.OPEN, expected_version=1)
    with pytest.raises(NotFoundError):
        await InboxService(db_session).detail(LOCAL_OWNER_ID, 987654321)


async def test_the_system_actions_are_not_available_to_the_owner(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    entry = await s.entry()
    for action in (A.SURFACE_NEW, A.MATERIAL_UPDATE):
        with pytest.raises(InputValidationError):
            await act(db_session, entry, action)


# --- listing -------------------------------------------------------------------------------------------------------------


async def titles(session: AsyncSession, s: Scene, **changes: Any) -> list[int]:
    page = await InboxService(session).list_items(LOCAL_OWNER_ID, s.filters(**changes), limit=50)
    return [row.item.job_inbox_item_id for row in page.rows]


async def test_the_default_state_filter_is_unread(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    unread = await s.entry()
    await s.entry(state=InboxState.READ)
    await s.entry(state=InboxState.IGNORED)
    ids = await titles(db_session, s, state="unread")
    assert ids == [unread.item.job_inbox_item_id]
    assert len(await titles(db_session, s, state=None)) == 3


async def test_filters_by_whether_the_job_has_a_score(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    scored = await s.entry(fit=70, days=1)
    unscored = await s.entry(days=2)

    assert await titles(db_session, s, evaluated=True) == [scored.item.job_inbox_item_id]
    assert await titles(db_session, s, evaluated=False) == [unscored.item.job_inbox_item_id]
    assert set(await titles(db_session, s, evaluated=None)) == {
        scored.item.job_inbox_item_id,
        unscored.item.job_inbox_item_id,
    }


async def test_filters_by_shortlist_company_source_date_and_fit(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    star = await s.entry(shortlisted=True, fit=90, days=1, company=f"{s.tag} Alpha Robotics")
    lever = await s.entry(
        fit=60, days=5, company=f"{s.tag} Beta Systems", source_type=SourceType.LEVER
    )
    unscored = await s.entry(days=10, company=f"{s.tag} Gamma Labs")

    assert await titles(db_session, s, shortlisted=True) == [star.item.job_inbox_item_id]
    assert await titles(db_session, s, company=f"{s.tag} alpha") == [
        star.item.job_inbox_item_id
    ]  # case-insensitive
    assert await titles(db_session, s, source="lever") == [lever.item.job_inbox_item_id]
    assert set(await titles(db_session, s, fit_min=61)) == {star.item.job_inbox_item_id}
    assert set(await titles(db_session, s, fit_max=70)) == {lever.item.job_inbox_item_id}
    assert set(await titles(db_session, s, fit_min=0)) == {
        star.item.job_inbox_item_id,
        lever.item.job_inbox_item_id,
    }  # unscored excluded
    assert await titles(db_session, s, first_seen_from=T0 + timedelta(days=8)) == [
        unscored.item.job_inbox_item_id
    ]
    assert await titles(db_session, s, first_seen_to=T0 + timedelta(days=2)) == [
        star.item.job_inbox_item_id
    ]


async def test_the_default_sort_is_fit_descending_then_newest_with_unscored_last(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    low_new = await s.entry(fit=50, days=9)
    high_old = await s.entry(fit=90, days=1)
    high_new = await s.entry(fit=90, days=3)
    unscored_new = await s.entry(days=20)
    unscored_old = await s.entry(days=2)
    ids = await titles(db_session, s)
    assert ids == [
        e.item.job_inbox_item_id for e in (high_new, high_old, low_new, unscored_new, unscored_old)
    ]


async def test_newest_and_oldest_sorts(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    old, mid, new = (
        await s.entry(fit=10, days=1),
        await s.entry(fit=99, days=5),
        await s.entry(fit=50, days=9),
    )
    assert await titles(db_session, s, sort="newest") == [
        e.item.job_inbox_item_id for e in (new, mid, old)
    ]
    assert await titles(db_session, s, sort="oldest") == [
        e.item.job_inbox_item_id for e in (old, mid, new)
    ]


async def test_scores_come_from_the_selected_intent_only(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    await s.entry(fit=40, other_fit=95)
    mine = (await InboxService(db_session).list_items(LOCAL_OWNER_ID, s.filters(), limit=5)).rows[0]
    other = (
        await InboxService(db_session).list_items(
            LOCAL_OWNER_ID, s.filters(search_intent_id=s.other_intent.search_intent_id), limit=5
        )
    ).rows[0]
    assert (mine.evaluation.fit_score, other.evaluation.fit_score) == (40, 95)  # type: ignore[union-attr]


async def test_a_job_without_an_evaluation_is_listed_as_not_evaluated(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    await s.entry()
    row = (await InboxService(db_session).list_items(LOCAL_OWNER_ID, s.filters(), limit=5)).rows[0]
    assert row.evaluation is None and row.dimensions == []


async def test_a_not_recommended_evaluation_is_reported_as_such(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    await s.entry(fit=70, recommendation=Recommendation.NOT_RECOMMENDED)
    row = (await InboxService(db_session).list_items(LOCAL_OWNER_ID, s.filters(), limit=5)).rows[0]
    assert row.evaluation is not None and row.evaluation.recommendation == "not_recommended"


async def test_set_aside_splits_unread_jobs_by_the_stored_recommendation(
    db_session: AsyncSession,
) -> None:
    """ADR-058: jobs the latest evaluation does not recommend are set aside, nothing else is."""
    s = await scene(db_session)
    fine = await s.entry(fit=70, days=1)
    blocked = await s.entry(fit=60, days=2, recommendation=Recommendation.NOT_RECOMMENDED)
    unscored = await s.entry(days=3)

    shown = await titles(db_session, s, set_aside=False)
    assert set(shown) == {fine.item.job_inbox_item_id, unscored.item.job_inbox_item_id}
    assert await titles(db_session, s, set_aside=True) == [blocked.item.job_inbox_item_id]
    assert len(await titles(db_session, s, set_aside=None)) == 3


async def test_the_counts_separate_set_aside_jobs_from_those_to_review(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)

    async def counts() -> dict[str, int]:
        page = await InboxService(db_session).list_items(LOCAL_OWNER_ID, s.filters(), limit=1)
        return page.counts

    before = await counts()  # other tests may have committed items, so compare differences
    await s.entry(fit=70, days=1)
    await s.entry(fit=60, days=2, recommendation=Recommendation.NOT_RECOMMENDED)
    await s.entry(state=InboxState.READ, fit=60, recommendation=Recommendation.NOT_RECOMMENDED)
    after = await counts()
    # "To review" no longer counts the set-aside job and a read job is not set aside.
    assert after["unread"] - before["unread"] == 1
    assert after["set_aside"] - before["set_aside"] == 1
    assert after["total"] - before["total"] == 3


@pytest.mark.parametrize("sort", ["fit_desc", "newest", "oldest"])
async def test_pagination_by_cursor_visits_every_item_once(
    db_session: AsyncSession, sort: str
) -> None:
    s = await scene(db_session)
    created = [
        await s.entry(fit=(i * 7) % 5 * 10 if i % 3 else None, days=i % 4) for i in range(11)
    ]
    service = InboxService(db_session)
    seen: list[int] = []
    cursor = None
    for _ in range(10):
        page = await service.list_items(
            LOCAL_OWNER_ID, s.filters(sort=sort), limit=4, cursor=cursor
        )
        seen += [row.item.job_inbox_item_id for row in page.rows]
        cursor = page.next_cursor
        if cursor is None:
            break
    assert sorted(seen) == sorted(e.item.job_inbox_item_id for e in created)
    assert len(seen) == len(set(seen))


async def test_a_bad_cursor_or_limit_is_rejected(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    with pytest.raises(InputValidationError):
        await InboxService(db_session).list_items(
            LOCAL_OWNER_ID, s.filters(), limit=5, cursor="not-a-cursor"
        )
    with pytest.raises(InputValidationError):
        await InboxService(db_session).list_items(
            LOCAL_OWNER_ID, s.filters(sort="nonsense"), limit=5
        )


async def test_closed_opportunities_are_hidden_unless_applied(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    open_entry = await s.entry()
    closed = await s.entry()
    closed.opportunity.closed_at = T0
    applied_closed = await s.entry(state=InboxState.APPLIED)
    applied_closed.opportunity.closed_at = T0
    await db_session.flush()
    assert set(await titles(db_session, s)) == {
        open_entry.item.job_inbox_item_id,
        applied_closed.item.job_inbox_item_id,
    }
    assert closed.item.job_inbox_item_id in await titles(db_session, s, include_closed=True)


async def test_counts_by_state_and_shortlist(db_session: AsyncSession) -> None:
    s = await scene(db_session)
    await s.entry()
    await s.entry(state=InboxState.READ, shortlisted=True)
    await s.entry(state=InboxState.IGNORED)
    page = await InboxService(db_session).list_items(LOCAL_OWNER_ID, s.filters(), limit=5)
    assert page.counts["unread"] >= 1 and page.counts["read"] >= 1 and page.counts["ignored"] >= 1
    assert page.counts["shortlisted"] >= 1 and page.counts["total"] >= 3


# --- detail ---------------------------------------------------------------------------------------------------------------------------


async def test_the_detail_has_the_job_its_sites_the_score_and_the_history(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    entry = await s.entry(fit=82, title="Detailed role")
    company = await db_session.get(Company, entry.posting.company_id)
    assert company is not None
    other_source = await make_source(db_session, company, source_type=SourceType.LEVER)
    second, _snap = await make_posting(db_session, other_source, title="Detailed role")
    from decimal import Decimal

    from jobs_radar.db.models import JobOpportunityLink

    db_session.add(
        JobOpportunityLink(
            job_opportunity_id=entry.opportunity.job_opportunity_id,
            job_posting_id=second.job_posting_id,
            state="possible",
            similarity=Decimal("0.8"),
            features_json={},
            method="dedup-v1",
        )
    )
    await db_session.flush()
    await act(db_session, entry, A.OPEN)

    detail = await InboxService(db_session).detail(
        LOCAL_OWNER_ID, entry.item.job_inbox_item_id, search_intent_id=s.intent.search_intent_id
    )
    assert detail.row.title == "Detailed role" and detail.description
    assert detail.row.evaluation is not None and detail.row.evaluation.fit_score == 82
    assert len(detail.dimensions) == 1 and detail.dimensions[0].explanation
    assert {p.posting.source_type for p in detail.postings} == {"greenhouse", "lever"}
    assert {p.link.state for p in detail.postings} == {"auto", "possible"}
    assert [e.action for e in detail.events] == ["open"]  # newest first


# --- material changes ---------------------------------------------------------------------------------------------------------------


async def test_a_material_change_moves_eligible_items_to_updated_unread_only(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    states = [
        InboxState.UNREAD,
        InboxState.READ,
        InboxState.UPDATED_UNREAD,
        InboxState.IGNORED,
        InboxState.ARCHIVED,
        InboxState.APPLIED,
    ]
    entries = [await s.entry(state=state) for state in states]
    service = InboxService(db_session)
    moved = 0
    for entry in entries:
        moved += await service.notify_material_change(entry.posting.job_posting_id)
    for entry in entries:
        await db_session.refresh(entry.item)
    assert [e.item.state for e in entries] == [
        "updated_unread",
        "updated_unread",
        "updated_unread",
        "ignored",
        "archived",
        "applied",
    ]
    assert moved == 2  # the third was already updated_unread: nothing to record
    events = (
        (
            await db_session.execute(
                select(InboxEvent).where(
                    InboxEvent.action == "material_update",
                    InboxEvent.job_inbox_item_id.in_([e.item.job_inbox_item_id for e in entries]),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 2 and {e.actor for e in events} == {"system"}


async def test_a_change_to_a_posting_without_an_inbox_item_does_nothing(
    db_session: AsyncSession,
) -> None:
    source = await make_source(db_session, await make_company(db_session))
    posting, _s = await make_posting(db_session, source)
    assert await InboxService(db_session).notify_material_change(posting.job_posting_id) == 0


def test_imports_used_by_the_scene_exist() -> None:
    assert SearchIntent and IntentRevision and ProfileRevision and JobExtraction and update


async def test_the_text_search_matches_title_company_and_description_ignoring_case(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    by_title = await s.entry(title=f"{s.tag} Kubernetes Platform Engineer")
    by_company = await s.entry(company=f"{s.tag} Quartz Robotics")
    plain = await s.entry(title=f"{s.tag} Account Manager")
    assert await titles(db_session, s, text="kubernetes") == [by_title.item.job_inbox_item_id]
    assert await titles(db_session, s, text="QUARTZ") == [by_company.item.job_inbox_item_id]
    assert await titles(db_session, s, text="no-such-text-anywhere") == []
    assert set(await titles(db_session, s, text=s.tag)) == {
        by_title.item.job_inbox_item_id,
        by_company.item.job_inbox_item_id,
        plain.item.job_inbox_item_id,
    }


async def test_the_text_search_looks_in_the_description_too(db_session: AsyncSession) -> None:
    from tests.factories import make_company, make_inbox_item, make_opportunity, make_source
    from tests.factories import make_posting as make

    s = await scene(db_session)
    source = await make_source(db_session, await make_company(db_session, f"{s.tag} Co"))
    posting, _snapshot = await make(
        db_session, source, title=f"{s.tag} role", description="We run Terraform and Ansible daily."
    )
    opportunity = await make_opportunity(db_session, posting)
    item = await make_inbox_item(db_session, opportunity)
    assert await titles(db_session, s, text="terraform") == [item.job_inbox_item_id]


async def test_wildcard_characters_in_the_search_are_taken_literally(
    db_session: AsyncSession,
) -> None:
    s = await scene(db_session)
    await s.entry(title=f"{s.tag} Plain title")
    assert await titles(db_session, s, text="%") == []
    assert await titles(db_session, s, text="_") == []
