"""Inbox endpoints (T4.8): list, detail, actions and decisions on possible duplicates."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.factories import make_posting, make_source
from tests.inbox_scene import T0, Entry, Scene, scene

from jobs_radar.db.models import JobOpportunityLink
from jobs_radar.domain.enums import InboxState, Recommendation, SourceType

pytestmark = pytest.mark.integration

API = "/api/v1"


async def committed(
    session_factory: async_sessionmaker[AsyncSession], build: Any
) -> tuple[Scene, list[Entry]]:
    """Build entries with ``build(scene) -> list[Entry]`` and commit them for the API to see."""
    async with session_factory() as session:
        s = await scene(session)
        entries = await build(s)
        await session.commit()
        return s, entries


def params(s: Scene, **extra: Any) -> dict[str, Any]:
    return {
        "search_intent_id": s.intent.search_intent_id,
        "company": s.tag,
        "state": "all",
        **extra,
    }


async def ids(client: httpx.AsyncClient, s: Scene, **extra: Any) -> list[int]:
    response = await client.get(f"{API}/inbox", params=params(s, **extra))
    assert response.status_code == 200, response.text
    return [item["job_inbox_item_id"] for item in response.json()["items"]]


# --- list ----------------------------------------------------------------------------------------------------


async def test_the_list_returns_cards_with_score_signals_and_sources(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    s, (scored, unscored) = await committed(session_factory, lambda s: _two(s))
    response = await client.get(f"{API}/inbox", params=params(s))
    assert response.status_code == 200
    body = response.json()
    first, second = body["items"]
    assert first["job_inbox_item_id"] == scored.item.job_inbox_item_id  # scored before unscored
    assert first["evaluated"] is True and first["evaluation"]["fit_score"] == 82
    assert (
        first["evaluation"]["fit_band"] == "excellent"
        and first["evaluation"]["recommendation"] == "recommended"
    )
    assert [sig["dimension_key"] for sig in first["signals"]] == ["skills_technology"]
    assert first["state"] == "unread" and first["version"] == 1 and first["is_shortlisted"] is False
    assert (
        first["sources"][0]["source_type"] == "greenhouse"
        and first["sources"][0]["link_state"] == "auto"
    )
    assert first["possible_duplicate"] is False and first["closed"] is False
    assert second["evaluated"] is False and second["evaluation"] is None and second["signals"] == []
    assert body["counts"]["total"] >= 2 and body["search_intent_id"] == s.intent.search_intent_id
    assert unscored.item.job_inbox_item_id == second["job_inbox_item_id"]


async def _two(s: Scene) -> list[Entry]:
    return [await s.entry(fit=82, title="Scored role"), await s.entry(title="Unscored role")]


async def test_default_state_is_unread_and_all_shows_everything(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    s, (unread, read) = await committed(
        session_factory,
        lambda s: _states(s),
    )
    default = await client.get(
        f"{API}/inbox", params={"search_intent_id": s.intent.search_intent_id, "company": s.tag}
    )
    assert [i["job_inbox_item_id"] for i in default.json()["items"]] == [
        unread.item.job_inbox_item_id
    ]
    assert set(await ids(client, s)) == {unread.item.job_inbox_item_id, read.item.job_inbox_item_id}


async def _states(s: Scene) -> list[Entry]:
    return [await s.entry(), await s.entry(state=InboxState.READ)]


async def test_the_set_aside_filter_and_count_are_exposed(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async def build(s: Scene) -> list[Entry]:
        return [
            await s.entry(fit=80, days=1),
            await s.entry(fit=60, days=2, recommendation=Recommendation.NOT_RECOMMENDED),
        ]

    s, (fine, blocked) = await committed(session_factory, build)
    assert await ids(client, s, set_aside="true") == [blocked.item.job_inbox_item_id]
    assert await ids(client, s, set_aside="false") == [fine.item.job_inbox_item_id]
    response = await client.get(
        f"{API}/inbox", params={"search_intent_id": s.intent.search_intent_id, "company": s.tag}
    )
    assert response.json()["counts"]["set_aside"] >= 1


async def test_filters_and_sorting_are_applied(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async def build(s: Scene) -> list[Entry]:
        return [
            await s.entry(fit=90, days=1, shortlisted=True),
            await s.entry(fit=50, days=5, source_type=SourceType.LEVER),
            await s.entry(days=9),
        ]

    s, (a, b, c) = await committed(session_factory, build)
    assert await ids(client, s, shortlisted="true") == [a.item.job_inbox_item_id]
    assert await ids(client, s, source="lever") == [b.item.job_inbox_item_id]
    assert await ids(client, s, fit_min=60) == [a.item.job_inbox_item_id]
    assert await ids(client, s, fit_max=60) == [b.item.job_inbox_item_id]
    assert await ids(client, s, evaluated="false") == [c.item.job_inbox_item_id]
    assert set(await ids(client, s, evaluated="true")) == {
        a.item.job_inbox_item_id,
        b.item.job_inbox_item_id,
    }
    assert await ids(client, s, sort="newest") == [
        c.item.job_inbox_item_id,
        b.item.job_inbox_item_id,
        a.item.job_inbox_item_id,
    ]
    assert await ids(client, s, sort="oldest") == [
        a.item.job_inbox_item_id,
        b.item.job_inbox_item_id,
        c.item.job_inbox_item_id,
    ]
    assert await ids(client, s, **{"from": (T0 + timedelta(days=8)).isoformat()}) == [
        c.item.job_inbox_item_id
    ]
    assert await ids(client, s, **{"to": (T0 + timedelta(days=2)).isoformat()}) == [
        a.item.job_inbox_item_id
    ]


async def test_the_cursor_pages_through_the_list(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async def build(s: Scene) -> list[Entry]:
        return [await s.entry(fit=i * 10, days=i) for i in range(7)]

    s, entries = await committed(session_factory, build)
    seen: list[int] = []
    cursor = None
    for _ in range(5):
        response = await client.get(
            f"{API}/inbox", params=params(s, limit=3, **({"cursor": cursor} if cursor else {}))
        )
        data = response.json()
        seen += [i["job_inbox_item_id"] for i in data["items"]]
        cursor = data["next_cursor"]
        if cursor is None:
            break
    assert sorted(seen) == sorted(e.item.job_inbox_item_id for e in entries) and len(seen) == 7


@pytest.mark.parametrize(
    "bad",
    [
        {"limit": 0},
        {"limit": 101},
        {"sort": "nonsense"},
        {"cursor": "garbage"},
        {"fit_min": 101},
        {"state": "bogus"},
        {"fit_max": -1},
    ],
)
async def test_invalid_list_parameters_are_rejected(
    client: httpx.AsyncClient, bad: dict[str, Any]
) -> None:
    assert (await client.get(f"{API}/inbox", params=bad)).status_code == 422


# --- detail ---------------------------------------------------------------------------------------------------------


async def test_the_detail_has_the_text_the_evidence_the_sites_and_the_history(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    s, (entry,) = await committed(session_factory, lambda s: _one(s))
    await client.post(
        f"{API}/inbox/{entry.item.job_inbox_item_id}/actions",
        json={"action": "open", "expected_version": 1},
    )
    response = await client.get(
        f"{API}/inbox/{entry.item.job_inbox_item_id}",
        params={"search_intent_id": s.intent.search_intent_id},
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["description_text"] and detail["title"] == "Detailed role"
    assert detail["evaluation"]["fit_score"] == 82
    (dimension,) = detail["dimensions"]
    assert (
        dimension["dimension_key"] == "skills_technology"
        and dimension["explanation"]
        and "evidence" in dimension
    )
    assert [e["action"] for e in detail["events"]] == ["open"]
    assert detail["read_at"] is not None and detail["last_change"] is None
    assert (await client.get(f"{API}/inbox/987654321")).status_code == 404


async def _one(s: Scene) -> list[Entry]:
    return [await s.entry(fit=82, title="Detailed role")]


# --- actions --------------------------------------------------------------------------------------------------------


async def post_action(
    client: httpx.AsyncClient, entry: Entry, body: dict[str, Any]
) -> httpx.Response:
    return await client.post(f"{API}/inbox/{entry.item.job_inbox_item_id}/actions", json=body)


async def test_actions_change_the_state_and_return_the_item_and_the_event(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    s, (entry,) = await committed(session_factory, lambda s: _one(s))
    opened = await post_action(client, entry, {"action": "open", "expected_version": 1})
    assert opened.status_code == 200
    assert opened.json()["item"]["state"] == "read" and opened.json()["item"]["version"] == 2
    assert opened.json()["event"]["action"] == "open" and opened.json()["event"]["actor"] == "user"

    ignored = await post_action(
        client,
        entry,
        {
            "action": "ignore",
            "expected_version": 2,
            "reason": "wrong_contract",
            "note": "Employee-only.",
        },
    )
    assert (
        ignored.json()["item"]["state"] == "ignored"
        and ignored.json()["item"]["note"] == "Employee-only."
    )
    restored = await post_action(client, entry, {"action": "restore", "expected_version": 3})
    assert restored.json()["item"]["state"] == "read"

    star = await post_action(client, entry, {"action": "shortlist", "expected_version": 4})
    assert star.json()["item"]["is_shortlisted"] is True and star.json()["item"]["state"] == "read"
    assert entry.item.job_inbox_item_id in await ids(client, s, shortlisted="true")

    applied = await post_action(
        client,
        entry,
        {
            "action": "record_application",
            "expected_version": 5,
            "applied_at": "2026-10-07T12:00:00Z",
            "application_url": "https://careers.example.test/apply",
        },
    )
    assert applied.json()["item"]["state"] == "applied" and applied.json()["item"][
        "applied_at"
    ].startswith("2026-10-07T12:00")
    undone = await post_action(client, entry, {"action": "restore", "expected_version": 6})
    assert undone.json()["item"]["state"] == "read" and undone.json()["item"]["applied_at"] is None


async def test_opening_an_already_read_item_returns_no_event(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    _s, (entry,) = await committed(session_factory, lambda s: _one(s))
    await post_action(client, entry, {"action": "open", "expected_version": 1})
    again = await post_action(client, entry, {"action": "open", "expected_version": 2})
    assert (
        again.status_code == 200
        and again.json()["event"] is None
        and again.json()["item"]["version"] == 2
    )


async def test_a_stale_version_is_409_and_an_invalid_transition_is_422(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    _s, (entry,) = await committed(session_factory, lambda s: _one(s))
    await post_action(client, entry, {"action": "open", "expected_version": 1})
    stale = await post_action(client, entry, {"action": "ignore", "expected_version": 1})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "conflict"
    invalid = await post_action(client, entry, {"action": "restore", "expected_version": 2})
    assert invalid.status_code == 422 and "not allowed" in invalid.json()["error"]["message"]
    assert (
        await client.post(
            f"{API}/inbox/987654321/actions", json={"action": "open", "expected_version": 1}
        )
    ).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"action": "open"},  # no expected version
        {"action": "surface_new", "expected_version": 1},  # system action
        {"action": "material_update", "expected_version": 1},
        {"action": "open", "expected_version": 0},
        {
            "action": "record_application",
            "expected_version": 1,
            "application_url": "javascript:alert(1)",
        },
        {"action": "ignore", "expected_version": 1, "note": "x" * 2001},
        {"action": "open", "expected_version": 1, "unexpected": True},
    ],
)
async def test_invalid_action_requests_are_rejected_and_change_nothing(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    body: dict[str, Any],
) -> None:
    _s, (entry,) = await committed(session_factory, lambda s: _one(s))
    assert (await post_action(client, entry, body)).status_code == 422
    async with session_factory() as session:
        from jobs_radar.db.models import JobInboxItem

        item = await session.get(JobInboxItem, entry.item.job_inbox_item_id)
        assert item is not None and (item.state, item.version) == ("unread", 1)


# --- possible duplicates -----------------------------------------------------------------------------------------------


async def possible_link(session_factory: async_sessionmaker[AsyncSession]) -> tuple[int, int, int]:
    async with session_factory() as session:
        s = await scene(session)
        entry = await s.entry(fit=80)
        from jobs_radar.db.models import Company

        company_row = await session.get(Company, entry.posting.company_id)
        assert company_row is not None
        lever = await make_source(session, company_row, source_type=SourceType.LEVER)
        second, _snapshot = await make_posting(session, lever, title="Scored role")
        link = JobOpportunityLink(
            job_opportunity_id=entry.opportunity.job_opportunity_id,
            job_posting_id=second.job_posting_id,
            state="possible",
            similarity=Decimal("0.8"),
            features_json={},
            method="dedup-v1",
        )
        session.add(link)
        await session.flush()
        link_id, opportunity_id, item_id = (
            link.job_opportunity_link_id,
            entry.opportunity.job_opportunity_id,
            entry.item.job_inbox_item_id,
        )
        await session.commit()
        return link_id, opportunity_id, item_id


async def test_a_possible_duplicate_is_flagged_on_the_card_and_can_be_confirmed(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    link_id, opportunity_id, item_id = await possible_link(session_factory)
    card = (await client.get(f"{API}/inbox/{item_id}")).json()
    assert card["possible_duplicate"] is True
    assert {src["link_state"] for src in card["sources"]} == {"auto", "possible"}
    confirmed = await client.post(f"{API}/opportunity-links/{link_id}/confirm")
    assert confirmed.status_code == 200 and confirmed.json() == {
        "job_opportunity_id": opportunity_id,
        "state": "confirmed",
    }
    assert (await client.get(f"{API}/inbox/{item_id}")).json()["possible_duplicate"] is False


async def test_rejecting_a_possible_duplicate_separates_the_listing(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    link_id, opportunity_id, item_id = await possible_link(session_factory)
    rejected = await client.post(f"{API}/opportunity-links/{link_id}/reject")
    assert rejected.status_code == 200 and rejected.json()["state"] == "rejected"
    assert rejected.json()["job_opportunity_id"] != opportunity_id
    card = (await client.get(f"{API}/inbox/{item_id}")).json()
    assert len(card["sources"]) == 1 and card["possible_duplicate"] is False
    assert (await client.post(f"{API}/opportunity-links/{link_id}/confirm")).status_code == 409
    assert (await client.post(f"{API}/opportunity-links/987654321/reject")).status_code == 404

    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(JobOpportunityLink).where(
                        JobOpportunityLink.job_opportunity_link_id == link_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert rows[0].state == "rejected"


async def test_the_text_search_parameter_narrows_the_list(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async def build(s: Scene) -> list[Entry]:
        return [
            await s.entry(title=f"{s.tag} Kubernetes Engineer"),
            await s.entry(title=f"{s.tag} Accountant"),
        ]

    s, (match, _other) = await committed(session_factory, build)
    assert await ids(client, s, q="KUBERNETES") == [match.item.job_inbox_item_id]
    assert (await client.get(f"{API}/inbox", params={"q": "x" * 201})).status_code == 422
