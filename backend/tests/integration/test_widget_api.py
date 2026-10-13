"""Dashboard widget summary (ADR-065): counts of jobs to review and the readiness of the stack."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.inbox_scene import scene

from jobs_radar.db.models import CompanyFollow
from jobs_radar.domain.enums import LOCAL_OWNER_ID, InboxState, Recommendation

pytestmark = pytest.mark.integration

URL = "/api/v1/widget/summary"


async def test_it_counts_unread_jobs_at_or_above_the_threshold(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        s = await scene(session)
        await session.commit()
    pin = {"fit_min": 65, "search_intent_id": s.intent.search_intent_id}
    before = (await client.get(URL, params=pin)).json()
    async with session_factory() as session:
        s.session = session
        await s.entry(fit=90)  # counts
        await s.entry(fit=65)  # the threshold itself counts
        await s.entry(fit=40)  # to review, below the threshold
        await s.entry()  # not evaluated: to review, no fit
        await s.entry(fit=95, state=InboxState.READ)  # already reviewed
        await s.entry(fit=99, recommendation=Recommendation.NOT_RECOMMENDED)  # set aside
        await session.commit()
    response = await client.get(URL, params=pin)
    assert response.status_code == 200, response.text
    after = response.json()
    assert after["fit_threshold"] == 65
    assert after["to_review"] - before["to_review"] == 4
    assert after["to_review_high_fit"] - before["to_review_high_fit"] == 2
    assert after["best_fit"] is not None and after["best_fit"] >= 90


async def test_the_threshold_defaults_to_65_and_is_validated(client: httpx.AsyncClient) -> None:
    default = await client.get(URL)
    assert default.status_code == 200 and default.json()["fit_threshold"] == 65
    assert (await client.get(URL, params={"fit_min": 101})).status_code == 422


async def test_it_reports_the_readiness_without_failing_when_a_part_is_down(
    client: httpx.AsyncClient,
) -> None:
    body = (await client.get(URL)).json()
    # Always 200 (the widget shows the state); the values are the same as /readyz.
    assert set(body["components"]) == {"database", "worker"}
    assert body["status"] in {"ready", "unavailable"}


async def test_it_counts_all_unread_and_recommended_jobs_of_followed_companies(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        s = await scene(session)
        await session.commit()
    pin = {"search_intent_id": s.intent.search_intent_id}
    before = (await client.get(URL, params=pin)).json()
    async with session_factory() as session:
        s.session = session
        followed = await s.entry(fit=80)  # followed, recommended, to review: counts
        await s.entry(fit=80)  # not followed
        low = await s.entry(fit=50)  # followed, recommended, below 65: still counts
        blocked = await s.entry(fit=90, recommendation=Recommendation.NOT_RECOMMENDED)
        read = await s.entry(fit=80, state=InboxState.READ)  # followed but already read
        unscored = await s.entry()  # followed, no verdict yet
        for entry in (followed, low, blocked, read, unscored):
            session.add(
                CompanyFollow(owner_id=LOCAL_OWNER_ID, company_id=entry.opportunity.company_id)
            )
        await session.commit()
    after = (await client.get(URL, params=pin)).json()
    assert after["followed_recommended"] - before["followed_recommended"] == 2
    # Unread in total includes the set-aside job, which "to review" leaves out.
    assert after["unread_total"] - before["unread_total"] == 5
    assert after["to_review"] - before["to_review"] == 4
