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
