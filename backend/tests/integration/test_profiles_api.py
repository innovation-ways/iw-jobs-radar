"""Profile, intent and taxonomy endpoints (T3.2)."""

from copy import deepcopy
from typing import Any

import httpx
import pytest
from tests.data import sample_intent, sample_profile_input
from tests.factories import unique

pytestmark = pytest.mark.integration

API = "/api/v1"


async def new_profile(client: httpx.AsyncClient, title: str | None = None) -> dict[str, Any]:
    response = await client.post(f"{API}/profiles", json={"title": title or unique("Profile")})
    assert response.status_code == 201, response.text
    return dict(response.json())


def save_body(expected: int | None, **changes: Any) -> dict[str, Any]:
    return {**sample_profile_input(), "expected_current_revision": expected, **changes}


async def save(client: httpx.AsyncClient, profile_id: int, expected: int | None, **changes: Any):  # type: ignore[no-untyped-def]
    return await client.put(f"{API}/profiles/{profile_id}", json=save_body(expected, **changes))


async def new_intent(client: httpx.AsyncClient, profile_id: int, **changes: Any) -> dict[str, Any]:
    body = {**deepcopy(sample_intent()), "enabled": True, **changes}
    response = await client.post(f"{API}/profiles/{profile_id}/intents", json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


# --- profiles -----------------------------------------------------------------------------------


async def test_creating_a_profile_returns_a_blank_profile(client: httpx.AsyncClient) -> None:
    profile = await new_profile(client, "Blank one")
    assert profile["title"] == "Blank one"
    assert profile["visibility"] == "private" and profile["version"] == 1
    assert profile["current_revision"] is None
    pid = profile["career_profile_id"]
    assert (await client.get(f"{API}/profiles/{pid}")).json()["title"] == "Blank one"
    listed = (await client.get(f"{API}/profiles")).json()["items"]
    assert pid in [p["career_profile_id"] for p in listed]


async def test_an_unknown_profile_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{API}/profiles/987654321")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_saving_creates_revision_one_and_names_the_skills(client: httpx.AsyncClient) -> None:
    pid = (await new_profile(client))["career_profile_id"]
    response = await save(client, pid, None, change_summary="First draft")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] is True
    revision = body["profile"]["current_revision"]
    assert (revision["revision_number"], revision["change_summary"]) == (1, "First draft")
    skills = revision["facts"]["skills"]
    assert [s["name"] for s in skills] == ["Python", "Kubernetes"]
    assert skills[0]["provenance"]["origin"] == "manual"
    assert revision["facts"]["headline"] == "AI solutions and integration engineer"
    assert revision["privacy"] == {
        "schema_version": 1,
        "redact_contact_details": True,
        "allow_cloud_processing": False,
    }


async def test_saving_without_changes_reports_created_false(client: httpx.AsyncClient) -> None:
    pid = (await new_profile(client))["career_profile_id"]
    await save(client, pid, None)
    again = await save(client, pid, 1)
    assert again.status_code == 200 and again.json()["created"] is False
    assert again.json()["profile"]["current_revision"]["revision_number"] == 1


async def test_a_stale_save_is_a_conflict(client: httpx.AsyncClient) -> None:
    pid = (await new_profile(client))["career_profile_id"]
    await save(client, pid, None)
    await save(client, pid, 1, headline="Two")
    stale = await save(client, pid, 1, headline="Three")
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "conflict"
    assert stale.json()["error"]["details"] == {"expected": 1, "actual": 2}


@pytest.mark.parametrize(
    "changes",
    [
        {"unknown_field": 1},
        {"headline": ""},
        {"years_experience": -1},
        {"skills": [{"name": "Python", "level": "expert", "years": 1}] * 2},
        {"experience": [{"title": "T", "organisation": "O", "start": "2020-05", "end": "2019-01"}]},
        {"expected_current_revision": "one"},
    ],
)
async def test_invalid_profile_input_is_rejected_without_echoing_values(
    client: httpx.AsyncClient, changes: dict[str, Any]
) -> None:
    pid = (await new_profile(client))["career_profile_id"]
    response = await client.put(f"{API}/profiles/{pid}", json=save_body(None, **changes))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_history_lists_summaries_newest_first_and_each_revision_can_be_read(
    client: httpx.AsyncClient,
) -> None:
    pid = (await new_profile(client))["career_profile_id"]
    await save(client, pid, None)
    await save(client, pid, 1, headline="Two")
    items = (await client.get(f"{API}/profiles/{pid}/revisions")).json()["items"]
    assert [r["revision_number"] for r in items] == [2, 1]
    assert "facts" not in items[0]
    one = (
        await client.get(f"{API}/profiles/{pid}/revisions/{items[1]['profile_revision_id']}")
    ).json()
    assert one["revision_number"] == 1 and one["facts"]["headline"].startswith("AI solutions")
    other = (await new_profile(client))["career_profile_id"]
    foreign = await client.get(
        f"{API}/profiles/{other}/revisions/{items[1]['profile_revision_id']}"
    )
    assert foreign.status_code == 404


async def test_restoring_creates_a_new_revision(client: httpx.AsyncClient) -> None:
    pid = (await new_profile(client))["career_profile_id"]
    await save(client, pid, None)
    await save(client, pid, 1, headline="Two")
    items = (await client.get(f"{API}/profiles/{pid}/revisions")).json()["items"]
    first_id = items[1]["profile_revision_id"]
    url = f"{API}/profiles/{pid}/revisions/{first_id}/restore"

    stale = await client.post(url, json={"expected_current_revision": 1})
    assert stale.status_code == 409
    ok = await client.post(url, json={"expected_current_revision": 2})
    assert ok.status_code == 200 and ok.json()["created"] is True
    current = ok.json()["profile"]["current_revision"]
    assert current["revision_number"] == 3 and current["change_summary"] == "Restored revision 1"
    assert current["facts"]["headline"].startswith("AI solutions")


async def test_export_has_profile_and_intents_but_no_secrets(client: httpx.AsyncClient) -> None:
    pid = (await new_profile(client, "Exported"))["career_profile_id"]
    await save(client, pid, None)
    await new_intent(client, pid)
    response = await client.get(f"{API}/profiles/{pid}/export")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 1 and body["profile"]["title"] == "Exported"
    assert body["profile"]["facts"]["skills"][0]["name"] == "Python"
    assert len(body["intents"]) == 1 and body["intents"][0]["definition"]["alert_threshold"] == 65
    text = response.text.lower()
    assert not any(word in text for word in ("credential", "password", "api_key", "ciphertext"))
    assert (await client.get(f"{API}/profiles/987654321/export")).status_code == 404


# --- intents ------------------------------------------------------------------------------------


async def test_creating_an_intent_returns_revision_one(client: httpx.AsyncClient) -> None:
    pid = (await new_profile(client))["career_profile_id"]
    intent = await new_intent(client, pid)
    assert intent["career_profile_id"] == pid and intent["enabled"] is True
    assert intent["version"] >= 1 and intent["title"] == sample_intent()["title"]
    revision = intent["current_revision"]
    assert revision["revision_number"] == 1
    assert revision["definition"]["weights"]["role_responsibilities"] == 25
    listed = (await client.get(f"{API}/profiles/{pid}/intents")).json()["items"]
    assert [i["search_intent_id"] for i in listed] == [intent["search_intent_id"]]


async def test_an_intent_outside_the_taxonomy_is_rejected_with_reasons(
    client: httpx.AsyncClient,
) -> None:
    pid = (await new_profile(client))["career_profile_id"]
    body = {**deepcopy(sample_intent()), "enabled": True}
    body["stances"]["role_families"].append({"key": "made_up_role", "stance": "preferred"})
    response = await client.post(f"{API}/profiles/{pid}/intents", json=body)
    assert response.status_code == 422
    assert "made_up_role" in str(response.json()["error"]["details"])
    missing = await client.post(
        f"{API}/profiles/987654321/intents", json={**sample_intent(), "enabled": True}
    )
    assert missing.status_code == 404


async def test_invalid_intent_rules_are_rejected(client: httpx.AsyncClient) -> None:
    pid = (await new_profile(client))["career_profile_id"]
    body = {**deepcopy(sample_intent()), "enabled": True}
    body["weights"] = dict.fromkeys(body["weights"], 0)
    assert (await client.post(f"{API}/profiles/{pid}/intents", json=body)).status_code == 422


async def test_saving_an_intent_uses_revisions_and_detects_no_change(
    client: httpx.AsyncClient,
) -> None:
    pid = (await new_profile(client))["career_profile_id"]
    iid = (await new_intent(client, pid))["search_intent_id"]
    url = f"{API}/intents/{iid}"

    same = await client.put(url, json={**sample_intent(), "expected_current_revision": 1})
    assert same.status_code == 200 and same.json()["created"] is False

    changed = deepcopy(sample_intent())
    changed["weights"]["compensation"] = 30
    ok = await client.put(
        url, json={**changed, "expected_current_revision": 1, "change_summary": "More pay"}
    )
    assert ok.json()["created"] is True
    revision = ok.json()["intent"]["current_revision"]
    assert revision["revision_number"] == 2 and revision["change_summary"] == "More pay"

    stale = await client.put(url, json={**changed, "expected_current_revision": 1})
    assert stale.status_code == 409


async def test_enable_and_disable_use_the_version(client: httpx.AsyncClient) -> None:
    pid = (await new_profile(client))["career_profile_id"]
    intent = await new_intent(client, pid)
    iid, version = intent["search_intent_id"], intent["version"]
    off = await client.post(f"{API}/intents/{iid}/disable", json={"expected_version": version})
    assert off.status_code == 200 and off.json()["enabled"] is False
    stale = await client.post(f"{API}/intents/{iid}/enable", json={"expected_version": version})
    assert stale.status_code == 409
    on = await client.post(
        f"{API}/intents/{iid}/enable", json={"expected_version": off.json()["version"]}
    )
    assert on.json()["enabled"] is True


async def test_intent_history_and_restore(client: httpx.AsyncClient) -> None:
    pid = (await new_profile(client))["career_profile_id"]
    iid = (await new_intent(client, pid))["search_intent_id"]
    changed = deepcopy(sample_intent())
    changed["alert_threshold"] = 80
    await client.put(f"{API}/intents/{iid}", json={**changed, "expected_current_revision": 1})

    items = (await client.get(f"{API}/intents/{iid}/revisions")).json()["items"]
    assert [r["revision_number"] for r in items] == [2, 1]
    assert items[0]["definition"]["alert_threshold"] == 80
    one = await client.get(f"{API}/intents/{iid}/revisions/{items[1]['intent_revision_id']}")
    assert one.json()["definition"]["alert_threshold"] == 65
    assert (await client.get(f"{API}/intents/{iid}/revisions/987654321")).status_code == 404

    restored = await client.post(
        f"{API}/intents/{iid}/revisions/{items[1]['intent_revision_id']}/restore",
        json={"expected_current_revision": 2},
    )
    assert restored.status_code == 200 and restored.json()["created"] is True
    current = restored.json()["intent"]["current_revision"]
    assert current["revision_number"] == 3 and current["definition"]["alert_threshold"] == 65


# --- taxonomy -----------------------------------------------------------------------------------


async def test_the_taxonomy_lists_terms_with_labels_by_kind(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{API}/taxonomy")
    assert response.status_code == 200
    groups = {g["kind"]: g["terms"] for g in response.json()["groups"]}
    assert {
        "role_family",
        "work_arrangement",
        "engagement_type",
        "seniority_level",
    } <= groups.keys()
    roles = {t["term_key"]: t["label"] for t in groups["role_family"]}
    assert roles.get("ai_solutions_engineering")
