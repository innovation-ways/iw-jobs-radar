"""The location scope is derived from the profile and the enabled intents (ADR-049.11)."""

from copy import deepcopy

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.data import sample_intent
from tests.factories import make_intent, make_profile

from jobs_radar.db.models import IntentRevision, SearchIntent
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.services.location_scope import LocationScopeService

pytestmark = pytest.mark.integration


async def only_ours(session: AsyncSession) -> None:
    """Disable intents committed by other tests; the rollback at the end undoes this."""
    await session.execute(update(SearchIntent).values(enabled=False))


async def scope(session: AsyncSession) -> LocationScope:
    return await LocationScopeService(session).for_owner(LOCAL_OWNER_ID)


async def enabled_intent(
    session: AsyncSession, *, remote: str = "preferred", regions: list[str] | None = None
) -> SearchIntent:
    profile, _ = await make_profile(session)
    intent, _ = await make_intent(session, profile)
    definition = deepcopy(sample_intent())
    for entry in definition["stances"]["work_arrangements"]:
        if entry["key"] == "remote":
            entry["stance"] = remote
    if regions is not None:
        definition["work_rules"]["remote"]["eligible_regions"] = regions
    revision2 = IntentRevision(
        search_intent_id=intent.search_intent_id, revision_number=2, intent_json=definition
    )
    session.add(revision2)
    await session.flush()
    intent.current_intent_revision_id = revision2.intent_revision_id
    intent.enabled = True
    await session.flush()
    return intent


async def test_without_an_enabled_intent_the_scope_is_empty(db_session: AsyncSession) -> None:
    await only_ours(db_session)
    assert (await scope(db_session)).is_empty


async def test_the_scope_has_the_profile_country_and_the_remote_regions(
    db_session: AsyncSession,
) -> None:
    await only_ours(db_session)
    await enabled_intent(db_session, regions=["EU"])
    result = await scope(db_session)
    assert {"PT", "DE", "ES"} <= result.country_codes
    assert result.include_worldwide is True
    assert result.any_country is False


async def test_a_disabled_intent_does_not_count(db_session: AsyncSession) -> None:
    await only_ours(db_session)
    intent = await enabled_intent(db_session)
    intent.enabled = False
    await db_session.flush()
    assert (await scope(db_session)).is_empty


async def test_an_intent_that_rejects_remote_work_adds_no_remote_regions(
    db_session: AsyncSession,
) -> None:
    await only_ours(db_session)
    await enabled_intent(db_session, remote="rejected", regions=["US"])
    result = await scope(db_session)
    assert result.country_codes == frozenset({"PT"})
    assert result.include_worldwide is False


async def test_worldwide_remote_regions_accept_any_country(db_session: AsyncSession) -> None:
    await only_ours(db_session)
    await enabled_intent(db_session, regions=["WORLD"])
    assert (await scope(db_session)).any_country is True
