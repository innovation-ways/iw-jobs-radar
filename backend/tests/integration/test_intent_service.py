"""Search-intent use cases: create, save, enable, history and restore (T3.1)."""

from copy import deepcopy
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.data import sample_intent
from tests.factories import make_profile, unique

from jobs_radar.core.errors import ConflictError, InputValidationError, NotFoundError
from jobs_radar.db.models import IntentRevision
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.services.intents import IntentService

pytestmark = pytest.mark.integration


def definition(**changes: Any) -> IntentDefinition:
    return IntentDefinition.model_validate({**deepcopy(sample_intent()), **changes})


async def new_profile_id(session: AsyncSession) -> int:
    return int((await make_profile(session))[0].career_profile_id)


async def revision_count(session: AsyncSession, intent_id: int) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(IntentRevision)
                .where(IntentRevision.search_intent_id == intent_id)
            )
        ).scalar_one()
    )


async def test_creating_an_intent_stores_revision_one(db_session: AsyncSession) -> None:
    service = IntentService(db_session)
    view = await service.create(
        LOCAL_OWNER_ID, await new_profile_id(db_session), definition(), enabled=True
    )
    assert view.intent.enabled is True and view.intent.title == definition().title
    assert view.current is not None and view.current.revision_number == 1
    assert view.current.intent_json["weights"]["role_responsibilities"] == 25


async def test_the_intent_must_match_the_live_taxonomy(db_session: AsyncSession) -> None:
    bad = deepcopy(sample_intent())
    bad["stances"]["role_families"].append({"key": "made_up_role", "stance": "preferred"})
    service = IntentService(db_session)
    with pytest.raises(InputValidationError) as error:
        await service.create(
            LOCAL_OWNER_ID,
            await new_profile_id(db_session),
            IntentDefinition.model_validate(bad),
            enabled=True,
        )
    assert "made_up_role" in str(error.value.details)


async def test_listing_intents_of_a_profile(db_session: AsyncSession) -> None:
    service = IntentService(db_session)
    profile_id = await new_profile_id(db_session)
    a = await service.create(LOCAL_OWNER_ID, profile_id, definition(title="A"), enabled=True)
    b = await service.create(LOCAL_OWNER_ID, profile_id, definition(title="B"), enabled=False)
    listed = await service.list_for_profile(LOCAL_OWNER_ID, profile_id)
    assert [v.intent.search_intent_id for v in listed] == [
        a.intent.search_intent_id,
        b.intent.search_intent_id,
    ]
    with pytest.raises(NotFoundError):
        await service.list_for_profile(LOCAL_OWNER_ID, 987654321)


async def test_saving_without_changes_creates_no_revision(db_session: AsyncSession) -> None:
    service = IntentService(db_session)
    view = await service.create(
        LOCAL_OWNER_ID, await new_profile_id(db_session), definition(), enabled=True
    )
    intent_id = view.intent.search_intent_id
    result = await service.save(
        LOCAL_OWNER_ID, intent_id, definition(), expected_current_revision=1
    )
    assert result.created is False
    assert await revision_count(db_session, intent_id) == 1


async def test_a_change_creates_the_next_revision_and_syncs_the_title(
    db_session: AsyncSession,
) -> None:
    service = IntentService(db_session)
    view = await service.create(
        LOCAL_OWNER_ID, await new_profile_id(db_session), definition(), enabled=True
    )
    changed = deepcopy(sample_intent())
    changed["weights"]["compensation"] = 30
    changed["title"] = unique("Renamed")
    result = await service.save(
        LOCAL_OWNER_ID,
        view.intent.search_intent_id,
        IntentDefinition.model_validate(changed),
        expected_current_revision=1,
        change_summary="More weight on pay",
    )
    assert result.created is True
    assert result.view.current is not None and result.view.current.revision_number == 2
    assert result.view.current.change_summary == "More weight on pay"
    assert result.view.intent.title == changed["title"]


async def test_a_stale_expectation_is_a_conflict(db_session: AsyncSession) -> None:
    service = IntentService(db_session)
    view = await service.create(
        LOCAL_OWNER_ID, await new_profile_id(db_session), definition(), enabled=True
    )
    intent_id = view.intent.search_intent_id
    await service.save(
        LOCAL_OWNER_ID, intent_id, definition(title="Two"), expected_current_revision=1
    )
    with pytest.raises(ConflictError):
        await service.save(
            LOCAL_OWNER_ID, intent_id, definition(title="Three"), expected_current_revision=1
        )
    assert await revision_count(db_session, intent_id) == 2


async def test_enabling_and_disabling_use_the_row_version(db_session: AsyncSession) -> None:
    service = IntentService(db_session)
    view = await service.create(
        LOCAL_OWNER_ID, await new_profile_id(db_session), definition(), enabled=True
    )
    intent_id, version = view.intent.search_intent_id, view.intent.version
    off = await service.set_enabled(
        LOCAL_OWNER_ID, intent_id, enabled=False, expected_version=version
    )
    assert off.intent.enabled is False and off.intent.version == version + 1
    with pytest.raises(ConflictError):
        await service.set_enabled(LOCAL_OWNER_ID, intent_id, enabled=True, expected_version=version)


async def test_history_and_restore(db_session: AsyncSession) -> None:
    service = IntentService(db_session)
    view = await service.create(
        LOCAL_OWNER_ID, await new_profile_id(db_session), definition(), enabled=True
    )
    intent_id = view.intent.search_intent_id
    changed = deepcopy(sample_intent())
    changed["alert_threshold"] = 80
    await service.save(
        LOCAL_OWNER_ID,
        intent_id,
        IntentDefinition.model_validate(changed),
        expected_current_revision=1,
    )
    history = await service.revisions(LOCAL_OWNER_ID, intent_id)
    assert [r.revision_number for r in history] == [2, 1]

    restored = await service.restore(
        LOCAL_OWNER_ID, intent_id, history[1].intent_revision_id, expected_current_revision=2
    )
    assert restored.created is True and restored.view.current is not None
    assert restored.view.current.revision_number == 3
    assert restored.view.current.intent_json["alert_threshold"] == 65
    assert restored.view.current.change_summary == "Restored revision 1"
    with pytest.raises(NotFoundError):
        await service.revision(LOCAL_OWNER_ID, intent_id, 987654321)
