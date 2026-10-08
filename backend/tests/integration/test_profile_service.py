"""Profile use cases: create, save as the next revision, history and restore (T3.1)."""

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.data import sample_profile_input
from tests.factories import unique

from jobs_radar.core.errors import ConflictError, NotFoundError
from jobs_radar.db.models import ProfileRevision, Skill
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.profile_api import ProfileInput
from jobs_radar.services.profiles import ProfileService

pytestmark = pytest.mark.integration


def data(**changes: Any) -> ProfileInput:
    return ProfileInput.model_validate({**sample_profile_input(), **changes})


async def revision_count(session: AsyncSession, profile_id: int) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(ProfileRevision)
                .where(ProfileRevision.career_profile_id == profile_id)
            )
        ).scalar_one()
    )


async def test_a_new_profile_is_blank_and_listed(db_session: AsyncSession) -> None:
    service = ProfileService(db_session)
    profile = await service.create(LOCAL_OWNER_ID, unique("Profile"))
    assert profile.current is None and profile.profile.version == 1
    listed = {p.profile.career_profile_id for p in await service.list_profiles(LOCAL_OWNER_ID)}
    assert profile.profile.career_profile_id in listed


async def test_the_first_save_creates_revision_one_with_manual_provenance(
    db_session: AsyncSession,
) -> None:
    service = ProfileService(db_session)
    pid = (await service.create(LOCAL_OWNER_ID, unique("P"))).profile.career_profile_id
    result = await service.save(
        LOCAL_OWNER_ID, pid, data(), expected_current_revision=None, change_summary="First draft"
    )
    assert result.created is True
    revision = result.view.revision
    assert (revision.revision_number, revision.change_summary) == (1, "First draft")
    skills = revision.facts_json["skills"]
    assert [result.view.skill_names[s["skill_id"]] for s in skills] == ["Python", "Kubernetes"]
    assert all(s["provenance"]["origin"] == "manual" for s in skills)
    assert revision.facts_json["experience"][0]["provenance"]["origin"] == "manual"
    got = await service.get(LOCAL_OWNER_ID, pid)
    assert got.current is not None and got.current.revision.revision_number == 1


async def test_saving_without_changes_creates_no_revision_and_keeps_provenance(
    db_session: AsyncSession,
) -> None:
    service = ProfileService(db_session)
    pid = (await service.create(LOCAL_OWNER_ID, unique("P"))).profile.career_profile_id
    first = await service.save(LOCAL_OWNER_ID, pid, data(), expected_current_revision=None)
    again = await service.save(LOCAL_OWNER_ID, pid, data(), expected_current_revision=1)
    assert again.created is False
    assert again.view.revision.profile_revision_id == first.view.revision.profile_revision_id
    assert await revision_count(db_session, pid) == 1


async def test_a_change_creates_the_next_revision_and_untouched_items_keep_their_provenance(
    db_session: AsyncSession,
) -> None:
    service = ProfileService(db_session)
    pid = (await service.create(LOCAL_OWNER_ID, unique("P"))).profile.career_profile_id
    first = await service.save(LOCAL_OWNER_ID, pid, data(), expected_current_revision=None)
    second = await service.save(
        LOCAL_OWNER_ID, pid, data(headline="Principal AI engineer"), expected_current_revision=1
    )
    assert second.created is True and second.view.revision.revision_number == 2
    assert second.view.revision.facts_json["headline"] == "Principal AI engineer"
    # the skills did not change, so they were not "re-accepted" now
    assert second.view.revision.facts_json["skills"] == first.view.revision.facts_json["skills"]
    assert (await service.get(LOCAL_OWNER_ID, pid)).profile.version == 3  # create + 2 revisions


async def test_a_stale_expectation_is_a_conflict_and_changes_nothing(
    db_session: AsyncSession,
) -> None:
    service = ProfileService(db_session)
    pid = (await service.create(LOCAL_OWNER_ID, unique("P"))).profile.career_profile_id
    await service.save(LOCAL_OWNER_ID, pid, data(), expected_current_revision=None)
    with pytest.raises(ConflictError):
        await service.save(LOCAL_OWNER_ID, pid, data(headline="X"), expected_current_revision=None)
    await service.save(LOCAL_OWNER_ID, pid, data(headline="Y"), expected_current_revision=1)
    with pytest.raises(ConflictError):
        await service.save(LOCAL_OWNER_ID, pid, data(headline="Z"), expected_current_revision=1)
    assert await revision_count(db_session, pid) == 2


async def test_a_stale_expectation_conflicts_even_when_nothing_changed(
    db_session: AsyncSession,
) -> None:
    service = ProfileService(db_session)
    pid = (await service.create(LOCAL_OWNER_ID, unique("P"))).profile.career_profile_id
    await service.save(LOCAL_OWNER_ID, pid, data(), expected_current_revision=None)
    await service.save(LOCAL_OWNER_ID, pid, data(headline="Y"), expected_current_revision=1)
    with pytest.raises(ConflictError):
        await service.save(LOCAL_OWNER_ID, pid, data(headline="Y"), expected_current_revision=1)


async def test_skill_names_resolve_to_one_skill_regardless_of_case_and_punctuation(
    db_session: AsyncSession,
) -> None:
    service = ProfileService(db_session)
    name = unique("Node.js")
    pid = (await service.create(LOCAL_OWNER_ID, unique("P"))).profile.career_profile_id
    skills = [{"name": name, "kind": "technology", "level": "advanced", "years": 3}]
    first = await service.save(
        LOCAL_OWNER_ID, pid, data(skills=skills), expected_current_revision=None
    )
    other = [{"name": name.upper(), "kind": "technology", "level": "expert", "years": 3}]
    second = await service.save(
        LOCAL_OWNER_ID, pid, data(skills=other), expected_current_revision=1
    )
    ids = {
        first.view.revision.facts_json["skills"][0]["skill_id"],
        second.view.revision.facts_json["skills"][0]["skill_id"],
    }
    assert len(ids) == 1
    count = await db_session.scalar(
        select(func.count())
        .select_from(Skill)
        .where(func.lower(Skill.canonical_name) == name.lower())
    )
    assert count == 1


async def test_the_same_skill_twice_is_rejected_by_validation() -> None:
    skills = [
        {"name": "Python", "kind": "technology", "level": "expert", "years": 1},
        {"name": "python", "kind": "technology", "level": "advanced", "years": 2},
    ]
    with pytest.raises(ValueError, match="duplicate"):
        data(skills=skills)


async def test_history_is_newest_first_and_each_revision_can_be_read(
    db_session: AsyncSession,
) -> None:
    service = ProfileService(db_session)
    pid = (await service.create(LOCAL_OWNER_ID, unique("P"))).profile.career_profile_id
    await service.save(LOCAL_OWNER_ID, pid, data(), expected_current_revision=None)
    await service.save(LOCAL_OWNER_ID, pid, data(headline="Two"), expected_current_revision=1)
    history = await service.revisions(LOCAL_OWNER_ID, pid)
    assert [v.revision.revision_number for v in history] == [2, 1]
    one = await service.revision(LOCAL_OWNER_ID, pid, history[1].revision.profile_revision_id)
    assert one.revision.facts_json["headline"] == "AI solutions and integration engineer"
    with pytest.raises(NotFoundError):
        await service.revision(LOCAL_OWNER_ID, pid, 987654321)


async def test_a_revision_of_another_profile_is_not_found(db_session: AsyncSession) -> None:
    service = ProfileService(db_session)
    a = (await service.create(LOCAL_OWNER_ID, unique("A"))).profile.career_profile_id
    b = (await service.create(LOCAL_OWNER_ID, unique("B"))).profile.career_profile_id
    saved = await service.save(LOCAL_OWNER_ID, a, data(), expected_current_revision=None)
    with pytest.raises(NotFoundError):
        await service.revision(LOCAL_OWNER_ID, b, saved.view.revision.profile_revision_id)


async def test_restoring_an_old_revision_creates_a_new_one_with_the_same_content(
    db_session: AsyncSession,
) -> None:
    service = ProfileService(db_session)
    pid = (await service.create(LOCAL_OWNER_ID, unique("P"))).profile.career_profile_id
    first = await service.save(LOCAL_OWNER_ID, pid, data(), expected_current_revision=None)
    await service.save(LOCAL_OWNER_ID, pid, data(headline="Changed"), expected_current_revision=1)
    restored = await service.restore(
        LOCAL_OWNER_ID,
        pid,
        first.view.revision.profile_revision_id,
        expected_current_revision=2,
    )
    assert restored.created is True and restored.view.revision.revision_number == 3
    assert restored.view.revision.facts_json == first.view.revision.facts_json
    assert restored.view.revision.change_summary == "Restored revision 1"
    # history is never rewritten
    assert await revision_count(db_session, pid) == 3
    with pytest.raises(ConflictError):
        await service.restore(
            LOCAL_OWNER_ID,
            pid,
            first.view.revision.profile_revision_id,
            expected_current_revision=2,
        )


async def test_restoring_the_current_revision_changes_nothing(db_session: AsyncSession) -> None:
    service = ProfileService(db_session)
    pid = (await service.create(LOCAL_OWNER_ID, unique("P"))).profile.career_profile_id
    first = await service.save(LOCAL_OWNER_ID, pid, data(), expected_current_revision=None)
    again = await service.restore(
        LOCAL_OWNER_ID, pid, first.view.revision.profile_revision_id, expected_current_revision=1
    )
    assert again.created is False and await revision_count(db_session, pid) == 1


async def test_unknown_profile_is_not_found(db_session: AsyncSession) -> None:
    service = ProfileService(db_session)
    with pytest.raises(NotFoundError):
        await service.get(LOCAL_OWNER_ID, 987654321)
    with pytest.raises(NotFoundError):
        await service.save(LOCAL_OWNER_ID, 987654321, data(), expected_current_revision=None)
