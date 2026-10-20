"""First-run setup: does this installation need it, and what do the packs suggest (ADR-080, 6c)."""

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import OwnerPack
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.repositories.revisions import ProfileRepository
from jobs_radar.services.packs import PackService
from jobs_radar.services.setup import SetupService

pytestmark = pytest.mark.integration


async def fresh_installation(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, *, profiles: int = 0
) -> None:
    """No pack switched on and ``profiles`` profiles, as on a newly installed copy.

    The shared test database may hold profiles other tests committed, so the profile count is
    stubbed instead of deleting rows.
    """
    await session.execute(delete(OwnerPack))
    await session.flush()

    async def listed(self: ProfileRepository, owner_id: int) -> list[object]:
        return [object()] * profiles

    monkeypatch.setattr(ProfileRepository, "list_for_owner", listed)


async def test_a_new_installation_needs_setup(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await fresh_installation(db_session, monkeypatch)
    status = await SetupService(db_session).status(LOCAL_OWNER_ID)
    assert (status.needs_setup, status.has_profile, status.active_pack_count) == (True, False, 0)


async def test_having_a_profile_or_a_pack_means_the_installation_is_set_up(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await fresh_installation(db_session, monkeypatch, profiles=1)
    only_profile = await SetupService(db_session).status(LOCAL_OWNER_ID)
    assert only_profile.needs_setup is False and only_profile.has_profile is True
    await fresh_installation(db_session, monkeypatch, profiles=0)
    await PackService(db_session).set_active(LOCAL_OWNER_ID, "healthcare_social", active=True)
    only_pack = await SetupService(db_session).status(LOCAL_OWNER_ID)
    assert only_pack.needs_setup is False and only_pack.active_pack_count == 1


async def test_the_defaults_come_from_the_first_pack_the_owner_switched_on(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await fresh_installation(db_session, monkeypatch)
    packs = PackService(db_session)
    await packs.set_active(LOCAL_OWNER_ID, "construction_trades", active=True)
    await packs.set_active(LOCAL_OWNER_ID, "software_data_it", active=True)
    defaults = await SetupService(db_session).intent_defaults(LOCAL_OWNER_ID)
    assert defaults.pack_key == "construction_trades"
    assert defaults.work_arrangements["onsite"] == "preferred"
    assert defaults.reject_missing_credentials is True
    # The pack's weights overlay the usual ones; every dimension has a weight.
    assert defaults.weights["qualifications"] > 0 and defaults.weights["compensation"] > 0
    assert set(defaults.weights) >= {"role_responsibilities", "schedule_travel", "career_direction"}


async def test_without_a_pack_there_are_no_suggestions_and_the_usual_weights(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await fresh_installation(db_session, monkeypatch)
    defaults = await SetupService(db_session).intent_defaults(LOCAL_OWNER_ID)
    assert defaults.pack_key is None and defaults.work_arrangements == {}
    assert (
        defaults.weights["role_responsibilities"] == 25 and defaults.weights["qualifications"] == 0
    )
    assert defaults.reject_missing_credentials is False


async def test_the_api_reports_the_status_and_the_defaults(
    isolated_client: httpx.AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await fresh_installation(db_session, monkeypatch)
    status = await isolated_client.get("/api/v1/setup/status")
    assert status.status_code == 200
    assert status.json() == {"needs_setup": True, "has_profile": False, "active_pack_count": 0}
    await PackService(db_session).set_active(LOCAL_OWNER_ID, "hospitality_tourism", active=True)
    defaults = (await isolated_client.get("/api/v1/setup/intent-defaults")).json()
    assert defaults["pack_key"] == "hospitality_tourism"
    assert defaults["work_arrangements"]["onsite"] == "preferred"
    assert isinstance(defaults["weights"]["schedule_travel"], int)
