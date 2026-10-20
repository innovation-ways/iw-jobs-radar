"""The areas of work the owner can filter job boards by (ADR-080, phase 5)."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.services.packs import PackService

pytestmark = pytest.mark.integration


async def test_the_areas_come_from_the_packs_that_are_on(
    isolated_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    response = await isolated_client.get("/api/v1/prefilter/areas")
    assert response.status_code == 200
    areas = response.json()["areas"]
    assert [a["key"] for a in areas] == ["software", "data", "devops", "security", "telecom"]
    assert areas[0] == {"key": "software", "label": "Software"}

    packs = PackService(db_session)
    await packs.set_active(LOCAL_OWNER_ID, "construction_trades", active=True)
    keys = [
        a["key"] for a in (await isolated_client.get("/api/v1/prefilter/areas")).json()["areas"]
    ]
    assert "electrical" in keys and "software" in keys

    await packs.set_active(LOCAL_OWNER_ID, "software_data_it", active=False)
    await packs.set_active(LOCAL_OWNER_ID, "construction_trades", active=False)
    assert (await isolated_client.get("/api/v1/prefilter/areas")).json() == {"areas": []}
