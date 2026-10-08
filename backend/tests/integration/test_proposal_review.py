"""Reviewing a proposal: accept, edit, reject, defer, atomically, into revision N+1 (T6.5)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.data import sample_profile_input

from jobs_radar.core.errors import ConflictError, InputValidationError, NotFoundError
from jobs_radar.db.models import Evidence, ProfileProposal, ProfileRevision, ProposalItem
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.profile_api import ProfileInput
from jobs_radar.services.profiles import ProfileService
from jobs_radar.services.proposal_review import Decision, ReviewService

pytestmark = pytest.mark.integration

LISBON = {"place": "Lisbon", "country": "PT"}


async def profile_with_revision(session: AsyncSession) -> tuple[int, int]:
    """A profile with a first manual revision; returns (profile id, revision number)."""
    service = ProfileService(session)
    profile = (await service.create(LOCAL_OWNER_ID, "Main")).profile
    saved = await service.save(
        LOCAL_OWNER_ID,
        profile.career_profile_id,
        ProfileInput.model_validate(sample_profile_input()),
        expected_current_revision=None,
    )
    return profile.career_profile_id, saved.view.revision.revision_number


async def blank_profile(session: AsyncSession) -> int:
    return (await ProfileService(session).create(LOCAL_OWNER_ID, "Blank")).profile.career_profile_id


async def proposal(
    session: AsyncSession, profile_id: int, *items: tuple[str, object]
) -> tuple[ProfileProposal, list[ProposalItem]]:
    row = ProfileProposal(
        owner_id=LOCAL_OWNER_ID,
        career_profile_id=profile_id,
        provider_type="ollama",
        provider_model="qwen3:8b",
        prompt_version="profile-import-v1",
    )
    session.add(row)
    await session.flush()
    rows = [
        ProposalItem(
            profile_proposal_id=row.profile_proposal_id,
            path=path,
            value_json=value,
            source_excerpt=f"excerpt for {path}",
            confidence=0.8,
        )
        for path, value in items
    ]
    session.add_all(rows)
    await session.flush()
    for r in [row, *rows]:
        await session.refresh(r)
    return row, rows


def accept(item: ProposalItem) -> Decision:
    return Decision(item.proposal_item_id, "accept")


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


async def test_accepted_items_become_the_next_revision_with_document_provenance(
    db_session: AsyncSession,
) -> None:
    profile_id, number = await profile_with_revision(db_session)
    row, items = await proposal(
        db_session,
        profile_id,
        ("skills", {"name": "Rust", "kind": "technology", "level": "advanced", "years": 3}),
        ("certifications", {"name": "Cloud Practitioner", "year": 2024}),
        ("headline", "Platform engineer"),
    )
    result = await ReviewService(db_session).review(
        LOCAL_OWNER_ID,
        profile_id,
        row.profile_proposal_id,
        [accept(i) for i in items],
        expected_current_revision=number,
    )
    assert result.created is True and result.revision_number == number + 1
    facts = result.view.revision.facts_json
    assert facts["headline"] == "Platform engineer"
    skills = {result.view.skill_names[s["skill_id"]]: s for s in facts["skills"]}
    assert set(skills) == {"Python", "Kubernetes", "Rust"}
    assert skills["Rust"]["provenance"]["origin"] == "document"
    assert skills["Rust"]["provenance"]["evidence_id"] is not None
    assert skills["Python"]["provenance"]["origin"] == "manual"  # untouched facts keep theirs
    assert {c["name"]: c["provenance"]["origin"] for c in facts["certifications"]} == {
        "Example Certification": "manual",
        "Cloud Practitioner": "document",
    }
    evidence = (
        await db_session.execute(
            select(Evidence).where(
                Evidence.evidence_id == skills["Rust"]["provenance"]["evidence_id"]
            )
        )
    ).scalar_one()
    assert (evidence.origin, evidence.excerpt) == ("document", "excerpt for skills")
    await db_session.refresh(row)
    assert row.status == "completed" and row.completed_at is not None


async def test_rejected_and_deferred_items_never_reach_a_revision(db_session: AsyncSession) -> None:
    profile_id, number = await profile_with_revision(db_session)
    row, (skill, cert, other) = await proposal(
        db_session,
        profile_id,
        ("skills", {"name": "Haskell", "kind": "technology", "level": "beginner", "years": 1}),
        ("certifications", {"name": "Secret Cert", "year": 2020}),
        ("skills", {"name": "Go", "kind": "technology", "level": "advanced", "years": 2}),
    )
    result = await ReviewService(db_session).review(
        LOCAL_OWNER_ID,
        profile_id,
        row.profile_proposal_id,
        [
            Decision(skill.proposal_item_id, "reject"),
            Decision(cert.proposal_item_id, "defer"),
            accept(other),
        ],
        expected_current_revision=number,
    )
    names = set(result.view.skill_names.values())
    assert "Go" in names and "Haskell" not in names
    assert "Secret Cert" not in str(result.view.revision.facts_json)
    states = {
        i.proposal_item_id: i.review_status
        for i in (
            await db_session.execute(
                select(ProposalItem).where(
                    ProposalItem.profile_proposal_id == row.profile_proposal_id
                )
            )
        ).scalars()
    }
    assert states == {
        skill.proposal_item_id: "rejected",
        cert.proposal_item_id: "deferred",
        other.proposal_item_id: "accepted",
    }


async def test_an_edited_value_is_validated_and_used(db_session: AsyncSession) -> None:
    profile_id, number = await profile_with_revision(db_session)
    row, (item,) = await proposal(
        db_session,
        profile_id,
        ("skills", {"name": "Pyhton", "kind": "technology", "level": "expert", "years": 9}),
    )
    result = await ReviewService(db_session).review(
        LOCAL_OWNER_ID,
        profile_id,
        row.profile_proposal_id,
        [
            Decision(
                item.proposal_item_id,
                "edit",
                {"name": "Python", "kind": "technology", "level": "expert", "years": 11},
            )
        ],
        expected_current_revision=number,
    )
    python = next(
        s
        for s in result.view.revision.facts_json["skills"]
        if result.view.skill_names[s["skill_id"]] == "Python"
    )
    assert python["years"] == 11 and python["provenance"]["origin"] == "document"
    await db_session.refresh(item)
    assert item.review_status == "edited" and item.edited_value_json["years"] == 11


async def test_only_rejecting_creates_no_revision_but_records_the_decisions(
    db_session: AsyncSession,
) -> None:
    profile_id, number = await profile_with_revision(db_session)
    row, (item,) = await proposal(db_session, profile_id, ("headline", "Different"))
    result = await ReviewService(db_session).review(
        LOCAL_OWNER_ID,
        profile_id,
        row.profile_proposal_id,
        [Decision(item.proposal_item_id, "reject")],
        expected_current_revision=number,
    )
    assert result.created is False and result.revision_number == number
    assert await revision_count(db_session, profile_id) == number
    await db_session.refresh(row)
    assert row.status == "completed"


async def test_a_blank_profile_needs_the_three_basics_before_its_first_revision(
    db_session: AsyncSession,
) -> None:
    profile_id = await blank_profile(db_session)
    row, (skill,) = await proposal(
        db_session,
        profile_id,
        ("skills", {"name": "Go", "kind": "technology", "level": "advanced", "years": 2}),
    )
    with pytest.raises(InputValidationError, match="headline"):
        await ReviewService(db_session).review(
            LOCAL_OWNER_ID,
            profile_id,
            row.profile_proposal_id,
            [accept(skill)],
            expected_current_revision=None,
        )
    await db_session.refresh(skill)
    assert skill.review_status == "pending"  # nothing was applied
    assert await revision_count(db_session, profile_id) == 0


async def test_a_first_revision_is_built_from_accepted_items_and_resolves_the_place(
    db_session: AsyncSession,
) -> None:
    profile_id = await blank_profile(db_session)
    row, items = await proposal(
        db_session,
        profile_id,
        ("headline", "Senior Software Engineer"),
        ("years_experience", 9),
        ("base_location", LISBON),
        ("languages", {"language": "en", "level": "C1"}),
    )
    result = await ReviewService(db_session).review(
        LOCAL_OWNER_ID,
        profile_id,
        row.profile_proposal_id,
        [accept(i) for i in items],
        expected_current_revision=None,
    )
    facts = result.view.revision.facts_json
    assert result.revision_number == 1 and facts["years_experience"] == 9
    assert (
        facts["base_location"]["timezone"] == "Europe/Lisbon"
        and facts["base_location"]["country"] == "PT"
    )
    assert facts["languages"] == [{"language": "en", "level": "C1"}]


async def test_an_unknown_place_must_be_edited(db_session: AsyncSession) -> None:
    profile_id = await blank_profile(db_session)
    row, (place,) = await proposal(
        db_session, profile_id, ("base_location", {"place": "Nowhereville", "country": "PT"})
    )
    with pytest.raises(InputValidationError, match="place"):
        await ReviewService(db_session).review(
            LOCAL_OWNER_ID,
            profile_id,
            row.profile_proposal_id,
            [accept(place)],
            expected_current_revision=None,
        )


async def test_a_stale_revision_or_a_decided_item_is_a_conflict_and_nothing_changes(
    db_session: AsyncSession,
) -> None:
    profile_id, number = await profile_with_revision(db_session)
    row, (item,) = await proposal(db_session, profile_id, ("headline", "New headline"))
    service = ReviewService(db_session)
    with pytest.raises(ConflictError):
        await service.review(
            LOCAL_OWNER_ID,
            profile_id,
            row.profile_proposal_id,
            [accept(item)],
            expected_current_revision=number + 5,
        )
    await service.review(
        LOCAL_OWNER_ID,
        profile_id,
        row.profile_proposal_id,
        [accept(item)],
        expected_current_revision=number,
    )
    with pytest.raises(ConflictError, match="already"):
        await service.review(
            LOCAL_OWNER_ID,
            profile_id,
            row.profile_proposal_id,
            [Decision(item.proposal_item_id, "reject")],
            expected_current_revision=number + 1,
        )


async def test_a_bad_decision_rolls_back_the_whole_review(db_session: AsyncSession) -> None:
    profile_id, number = await profile_with_revision(db_session)
    row, (good, bad) = await proposal(
        db_session,
        profile_id,
        ("headline", "Fine"),
        ("skills", {"name": "X", "kind": "technology", "level": "wizard", "years": 1}),
    )
    with pytest.raises(InputValidationError):
        await ReviewService(db_session).review(
            LOCAL_OWNER_ID,
            profile_id,
            row.profile_proposal_id,
            [accept(good), accept(bad)],
            expected_current_revision=number,
        )
    await db_session.refresh(good)
    assert (
        good.review_status == "pending" and await revision_count(db_session, profile_id) == number
    )


async def test_unknown_items_proposals_and_profiles_are_404(db_session: AsyncSession) -> None:
    profile_id, number = await profile_with_revision(db_session)
    row, _ = await proposal(db_session, profile_id, ("headline", "x"))
    service = ReviewService(db_session)
    with pytest.raises(NotFoundError):
        await service.review(
            LOCAL_OWNER_ID,
            profile_id,
            row.profile_proposal_id,
            [Decision(999_999, "accept")],
            expected_current_revision=number,
        )
    with pytest.raises(NotFoundError):
        await service.review(
            LOCAL_OWNER_ID, profile_id, 999_999, [], expected_current_revision=number
        )
    with pytest.raises(NotFoundError):
        await service.review(
            LOCAL_OWNER_ID, 999_999, row.profile_proposal_id, [], expected_current_revision=number
        )


async def test_an_edit_needs_a_value(db_session: AsyncSession) -> None:
    profile_id, number = await profile_with_revision(db_session)
    row, (item,) = await proposal(db_session, profile_id, ("headline", "x"))
    with pytest.raises(InputValidationError, match="value"):
        await ReviewService(db_session).review(
            LOCAL_OWNER_ID,
            profile_id,
            row.profile_proposal_id,
            [Decision(item.proposal_item_id, "edit")],
            expected_current_revision=number,
        )
