"""Ignoring a company moves its offers to Ignored; undoing restores only those (ADR-061)."""

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.factories import (
    make_company,
    make_inbox_item,
    make_opportunity,
    make_posting,
    make_source,
)

from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import Company, CompanyIgnore, InboxEvent, JobInboxItem
from jobs_radar.domain.enums import LOCAL_OWNER_ID, InboxAction, InboxState
from jobs_radar.services.companies import CompanyService
from jobs_radar.services.inbox import InboxService

pytestmark = pytest.mark.integration

BASE = "/api/v1"


async def offer(session: AsyncSession, company: Company, *, surface: bool = True) -> int:
    """One open opportunity of ``company`` (with an unread item unless ``surface`` is off)."""
    source = await make_source(session, company)
    posting, _snapshot = await make_posting(session, source)
    opportunity = await make_opportunity(session, posting)
    if surface:
        await make_inbox_item(session, opportunity)
    return opportunity.job_opportunity_id


async def state_of(session: AsyncSession, opportunity_id: int) -> JobInboxItem:
    """The owner's item for the opportunity, fresh from the database."""
    item = (
        await session.execute(
            select(JobInboxItem).where(JobInboxItem.job_opportunity_id == opportunity_id)
        )
    ).scalar_one()
    await session.refresh(item)
    return item


async def test_ignoring_moves_open_items_and_records_system_events(
    db_session: AsyncSession,
) -> None:
    company = await make_company(db_session)
    first = await offer(db_session, company)
    second = await offer(db_session, company)
    await CompanyService(db_session).set_ignored(LOCAL_OWNER_ID, company.company_id, ignored=True)

    for opportunity_id in (first, second):
        item = await state_of(db_session, opportunity_id)
        assert item.state == InboxState.IGNORED.value
        assert item.ignore_reason == "company_ignored"
        event = (
            (
                await db_session.execute(
                    select(InboxEvent)
                    .where(InboxEvent.job_inbox_item_id == item.job_inbox_item_id)
                    .order_by(InboxEvent.inbox_event_id.desc())
                )
            )
            .scalars()
            .first()
        )
        assert event is not None
        assert (event.action, event.actor) == (InboxAction.IGNORE.value, "system")


async def test_ignoring_leaves_other_companies_and_archived_or_applied_items_alone(
    db_session: AsyncSession,
) -> None:
    company = await make_company(db_session)
    other = await make_company(db_session)
    archived = await offer(db_session, company)
    applied = await offer(db_session, company)
    elsewhere = await offer(db_session, other)
    (await state_of(db_session, archived)).state = InboxState.ARCHIVED.value
    (await state_of(db_session, applied)).state = InboxState.APPLIED.value
    await db_session.flush()

    await CompanyService(db_session).set_ignored(LOCAL_OWNER_ID, company.company_id, ignored=True)

    assert (await state_of(db_session, archived)).state == InboxState.ARCHIVED.value
    assert (await state_of(db_session, applied)).state == InboxState.APPLIED.value
    assert (await state_of(db_session, elsewhere)).state == InboxState.UNREAD.value


async def test_an_opportunity_without_an_item_gets_an_ignored_one(
    db_session: AsyncSession,
) -> None:
    company = await make_company(db_session)
    opportunity_id = await offer(db_session, company, surface=False)
    await CompanyService(db_session).set_ignored(LOCAL_OWNER_ID, company.company_id, ignored=True)
    assert (await state_of(db_session, opportunity_id)).state == InboxState.IGNORED.value


async def test_new_offers_of_an_ignored_company_are_surfaced_as_ignored(
    db_session: AsyncSession,
) -> None:
    company = await make_company(db_session)
    await CompanyService(db_session).set_ignored(LOCAL_OWNER_ID, company.company_id, ignored=True)
    opportunity_id = await offer(db_session, company, surface=False)

    await InboxService(db_session).surface_new(LOCAL_OWNER_ID)

    item = await state_of(db_session, opportunity_id)
    assert (item.state, item.ignore_reason) == (InboxState.IGNORED.value, "company_ignored")


async def test_undoing_restores_only_what_the_company_ignore_moved(
    db_session: AsyncSession,
) -> None:
    company = await make_company(db_session)
    by_company = await offer(db_session, company)
    by_hand = await offer(db_session, company)
    manual = await state_of(db_session, by_hand)
    manual.state = InboxState.IGNORED.value
    manual.ignore_reason = "not_interested"
    await db_session.flush()

    service = CompanyService(db_session)
    await service.set_ignored(LOCAL_OWNER_ID, company.company_id, ignored=True)
    await service.set_ignored(LOCAL_OWNER_ID, company.company_id, ignored=False)

    restored = await state_of(db_session, by_company)
    assert (restored.state, restored.ignore_reason) == (InboxState.READ.value, None)
    assert (await state_of(db_session, by_hand)).state == InboxState.IGNORED.value
    count = (
        await db_session.execute(
            select(func.count())
            .select_from(CompanyIgnore)
            .where(CompanyIgnore.company_id == company.company_id)
        )
    ).scalar_one()
    assert count == 0
    # After undoing, new offers are surfaced as unread again.
    fresh = await offer(db_session, company, surface=False)
    await InboxService(db_session).surface_new(LOCAL_OWNER_ID)
    assert (await state_of(db_session, fresh)).state == InboxState.UNREAD.value


async def test_repeating_the_call_changes_nothing(db_session: AsyncSession) -> None:
    company = await make_company(db_session)
    opportunity_id = await offer(db_session, company)
    service = CompanyService(db_session)
    await service.set_ignored(LOCAL_OWNER_ID, company.company_id, ignored=True)
    version = (await state_of(db_session, opportunity_id)).version
    await service.set_ignored(LOCAL_OWNER_ID, company.company_id, ignored=True)
    assert (await state_of(db_session, opportunity_id)).version == version


async def test_an_unknown_company_raises_not_found(db_session: AsyncSession) -> None:
    with pytest.raises(NotFoundError):
        await CompanyService(db_session).set_ignored(LOCAL_OWNER_ID, 999999999, ignored=True)


async def test_the_api_ignores_and_unignores_and_reports_it_in_the_list(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        company = await make_company(session, "Ignore API Co")
        await session.commit()
        company_id = company.company_id
    url = f"{BASE}/companies/{company_id}/ignore"

    for _ in range(2):
        response = await client.put(url)
        assert response.status_code == 200, response.text
        assert response.json() == {"company_id": company_id, "is_ignored": True}
    listed = await client.get(f"{BASE}/companies", params={"q": "Ignore API Co"})
    assert [c["is_ignored"] for c in listed.json()["items"]] == [True]

    response = await client.delete(url)
    assert response.json() == {"company_id": company_id, "is_ignored": False}
    assert (await client.delete(f"{BASE}/companies/999999999/ignore")).status_code == 404
