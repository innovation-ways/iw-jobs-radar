"""GET and PUT /settings/schedule (T5.2)."""

import httpx
import pytest

pytestmark = pytest.mark.integration

URL = "/api/v1/settings/schedule"


async def test_the_schedule_can_be_read_and_changed_with_the_version_the_owner_saw(
    client: httpx.AsyncClient,
) -> None:
    current = (await client.get(URL)).json()
    assert set(current) == {
        "run_time_local",
        "timezone",
        "enabled",
        "company_recency_days",
        "set_aside_below_fit",
        "version",
        "next_run_at",
        "next_run_local",
    }
    saved = await client.put(
        URL,
        json={
            "run_time_local": "08:15",
            "timezone": "Europe/Lisbon",
            "enabled": True,
            "expected_version": current["version"],
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert (body["run_time_local"], body["timezone"], body["enabled"]) == (
        "08:15",
        "Europe/Lisbon",
        True,
    )
    assert body["version"] == current["version"] + 1
    assert body["next_run_at"] is not None and body["next_run_local"].endswith("08:15")

    off = await client.put(
        URL,
        json={
            "run_time_local": "08:15",
            "timezone": "Europe/Lisbon",
            "enabled": False,
            "expected_version": body["version"],
        },
    )
    assert off.json()["next_run_at"] is None and off.json()["next_run_local"] is None


async def test_the_company_recency_limit_defaults_to_30_and_keeps_its_value_when_omitted(
    client: httpx.AsyncClient,
) -> None:
    current = (await client.get(URL)).json()
    assert current["company_recency_days"] == 30
    base = {"run_time_local": "07:30", "timezone": "UTC", "enabled": False}
    changed = await client.put(
        URL, json={**base, "company_recency_days": 14, "expected_version": current["version"]}
    )
    assert changed.json()["company_recency_days"] == 14
    kept = await client.put(URL, json={**base, "expected_version": changed.json()["version"]})
    assert kept.json()["company_recency_days"] == 14  # omitted keeps the stored value
    for bad in (0, 366):
        response = await client.put(
            URL,
            json={**base, "company_recency_days": bad, "expected_version": kept.json()["version"]},
        )
        assert response.status_code == 422
    reset = await client.put(
        URL, json={**base, "company_recency_days": 30, "expected_version": kept.json()["version"]}
    )
    assert reset.json()["company_recency_days"] == 30


async def test_the_set_aside_floor_defaults_to_20_and_keeps_its_value_when_omitted(
    client: httpx.AsyncClient,
) -> None:
    """ADR-060: one inbox floor for the whole owner, 0 turns it off."""
    current = (await client.get(URL)).json()
    assert current["set_aside_below_fit"] == 20
    base = {"run_time_local": "07:30", "timezone": "UTC", "enabled": False}
    changed = await client.put(
        URL, json={**base, "set_aside_below_fit": 35, "expected_version": current["version"]}
    )
    assert changed.json()["set_aside_below_fit"] == 35
    kept = await client.put(URL, json={**base, "expected_version": changed.json()["version"]})
    assert kept.json()["set_aside_below_fit"] == 35  # omitted keeps the stored value
    off = await client.put(
        URL, json={**base, "set_aside_below_fit": 0, "expected_version": kept.json()["version"]}
    )
    assert off.json()["set_aside_below_fit"] == 0
    for bad in (-1, 101):
        response = await client.put(
            URL,
            json={**base, "set_aside_below_fit": bad, "expected_version": off.json()["version"]},
        )
        assert response.status_code == 422
    reset = await client.put(
        URL, json={**base, "set_aside_below_fit": 20, "expected_version": off.json()["version"]}
    )
    assert reset.json()["set_aside_below_fit"] == 20


async def test_a_stale_version_is_409_and_bad_input_is_422(client: httpx.AsyncClient) -> None:
    current = (await client.get(URL)).json()
    good = {"run_time_local": "07:30", "timezone": "UTC", "enabled": False}
    assert (
        await client.put(URL, json={**good, "expected_version": current["version"] + 5})
    ).status_code == 409
    for bad in (
        {**good, "timezone": "Mars/Phobos"},
        {**good, "run_time_local": "25:00"},
        {**good, "run_time_local": "7h30"},
        {**good, "unexpected": 1},
    ):
        assert (
            await client.put(URL, json={**bad, "expected_version": current["version"]})
        ).status_code == 422
    assert (await client.put(URL, json=good)).status_code == 422  # no expected version
