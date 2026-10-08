"""Creating the next profile or intent revision with an optimistic check (LLD section 7, ADR-030)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.data import sample_intent, sample_profile_facts

from jobs_radar.core.errors import ConflictError, NotFoundError
from jobs_radar.db.models import IntentRevision, ProfileRevision
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.repositories.revisions import IntentRepository, ProfileRepository
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.profile import ProfileFacts, ProfilePrivacy

pytestmark = pytest.mark.integration


def facts(headline: str = "AI solutions and integration engineer") -> ProfileFacts:
    data = sample_profile_facts()
    data["headline"] = headline
    return ProfileFacts.model_validate(data)


async def new_profile(session: AsyncSession) -> tuple[ProfileRepository, int]:
    repository = ProfileRepository(session)
    profile = await repository.create(owner_id=LOCAL_OWNER_ID, title="Synthetic profile")
    return repository, profile.career_profile_id


async def test_a_new_profile_has_no_revision_yet(db_session: AsyncSession) -> None:
    repository, profile_id = await new_profile(db_session)
    profile = await repository.get(LOCAL_OWNER_ID, profile_id)
    assert profile.current_profile_revision_id is None
    assert await repository.current_revision(profile) is None


async def test_the_first_revision_is_number_one_and_becomes_current(
    db_session: AsyncSession,
) -> None:
    repository, profile_id = await new_profile(db_session)
    profile = await repository.get(LOCAL_OWNER_ID, profile_id)
    revision = await repository.add_revision(
        profile,
        facts=facts(),
        privacy=ProfilePrivacy(),
        expected_current_revision=None,
        change_summary="Created",
    )
    assert revision.revision_number == 1
    assert profile.current_profile_revision_id == revision.profile_revision_id
    assert profile.version == 2  # created at 1, bumped by the new revision
    assert revision.facts_json["headline"] == "AI solutions and integration engineer"


async def test_the_next_revision_needs_the_current_number(db_session: AsyncSession) -> None:
    repository, profile_id = await new_profile(db_session)
    profile = await repository.get(LOCAL_OWNER_ID, profile_id)
    await repository.add_revision(
        profile, facts=facts(), privacy=ProfilePrivacy(), expected_current_revision=None
    )
    second = await repository.add_revision(
        profile, facts=facts("Changed"), privacy=ProfilePrivacy(), expected_current_revision=1
    )
    assert second.revision_number == 2
    assert (await repository.current_revision(profile)).revision_number == 2  # type: ignore[union-attr]


async def test_a_stale_expected_revision_is_a_conflict_and_changes_nothing(
    db_session: AsyncSession,
) -> None:
    repository, profile_id = await new_profile(db_session)
    profile = await repository.get(LOCAL_OWNER_ID, profile_id)
    await repository.add_revision(
        profile, facts=facts(), privacy=ProfilePrivacy(), expected_current_revision=None
    )
    await repository.add_revision(
        profile, facts=facts("B"), privacy=ProfilePrivacy(), expected_current_revision=1
    )

    with pytest.raises(ConflictError) as error:
        await repository.add_revision(
            profile, facts=facts("C"), privacy=ProfilePrivacy(), expected_current_revision=1
        )
    assert error.value.details == {"expected": 1, "actual": 2}
    count = await db_session.execute(
        select(func.count())
        .select_from(ProfileRevision)
        .where(ProfileRevision.career_profile_id == profile_id)
    )
    assert count.scalar_one() == 2


async def test_expecting_no_revision_when_one_exists_is_a_conflict(
    db_session: AsyncSession,
) -> None:
    repository, profile_id = await new_profile(db_session)
    profile = await repository.get(LOCAL_OWNER_ID, profile_id)
    await repository.add_revision(
        profile, facts=facts(), privacy=ProfilePrivacy(), expected_current_revision=None
    )
    with pytest.raises(ConflictError):
        await repository.add_revision(
            profile, facts=facts(), privacy=ProfilePrivacy(), expected_current_revision=None
        )


async def test_unknown_or_foreign_profiles_are_not_found(db_session: AsyncSession) -> None:
    repository = ProfileRepository(db_session)
    with pytest.raises(NotFoundError):
        await repository.get(LOCAL_OWNER_ID, 123456789)
    _, profile_id = await new_profile(db_session)
    with pytest.raises(NotFoundError):
        await repository.get(owner_id=999, career_profile_id=profile_id)


async def test_list_returns_only_the_owners_profiles(db_session: AsyncSession) -> None:
    repository, profile_id = await new_profile(db_session)
    ids = [profile.career_profile_id for profile in await repository.list_for_owner(LOCAL_OWNER_ID)]
    assert profile_id in ids
    assert await repository.list_for_owner(999) == []


# --- intents -------------------------------------------------------------------------------------


async def test_intent_revisions_follow_the_same_rules(db_session: AsyncSession) -> None:
    _, profile_id = await new_profile(db_session)
    intents = IntentRepository(db_session)
    intent = await intents.create(
        owner_id=LOCAL_OWNER_ID, career_profile_id=profile_id, title="Synthetic intent"
    )
    definition = IntentDefinition.model_validate(sample_intent())

    first = await intents.add_revision(
        intent, definition=definition, expected_current_revision=None
    )
    assert first.revision_number == 1
    assert intent.current_intent_revision_id == first.intent_revision_id

    second = await intents.add_revision(
        intent, definition=definition, expected_current_revision=1, change_summary="x"
    )
    assert second.revision_number == 2

    with pytest.raises(ConflictError) as error:
        await intents.add_revision(intent, definition=definition, expected_current_revision=1)
    assert error.value.details == {"expected": 1, "actual": 2}

    count = await db_session.execute(
        select(func.count())
        .select_from(IntentRevision)
        .where(IntentRevision.search_intent_id == intent.search_intent_id)
    )
    assert count.scalar_one() == 2


async def test_an_intent_must_belong_to_an_existing_profile_of_the_owner(
    db_session: AsyncSession,
) -> None:
    intents = IntentRepository(db_session)
    with pytest.raises(NotFoundError):
        await intents.create(owner_id=LOCAL_OWNER_ID, career_profile_id=123456789, title="Orphan")


async def test_enabling_and_disabling_an_intent_bumps_its_version(db_session: AsyncSession) -> None:
    _, profile_id = await new_profile(db_session)
    intents = IntentRepository(db_session)
    intent = await intents.create(
        owner_id=LOCAL_OWNER_ID, career_profile_id=profile_id, title="Toggle"
    )
    version = intent.version
    await intents.set_enabled(intent, enabled=False, expected_version=version)
    assert intent.enabled is False
    assert intent.version == version + 1
    with pytest.raises(ConflictError):
        await intents.set_enabled(intent, enabled=True, expected_version=version)  # stale
