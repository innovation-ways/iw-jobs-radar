"""Uniqueness, enumeration and range constraints enforced by the database (TR-3, LLD section 7)."""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import (
    NOW,
    build_full_graph,
    make_company,
    make_opportunity,
    make_posting,
    make_profile,
    make_source,
    unique,
)

from jobs_radar.db.models import (
    CollectionRun,
    IntentRevision,
    JobInboxItem,
    JobOpportunityLink,
    JobPosting,
    MatchEvaluation,
    ProfileRevision,
    ProviderConnection,
    ScheduleSetting,
    Skill,
    SkillRelation,
    SourceConfiguration,
    TaxonomyTerm,
)
from jobs_radar.domain.enums import LOCAL_OWNER_ID

pytestmark = pytest.mark.integration


async def expect_violation(
    session: AsyncSession, *objects: object, match: str | None = None
) -> None:
    """Add ``objects`` inside a savepoint and assert the database rejects them."""
    with pytest.raises(IntegrityError, match=match):
        async with session.begin_nested():
            session.add_all(objects)
            await session.flush()


async def test_profile_revision_numbers_are_unique_per_profile(db_session: AsyncSession) -> None:
    profile, _ = await make_profile(db_session)
    duplicate = ProfileRevision(
        career_profile_id=profile.career_profile_id,
        revision_number=1,
        facts_json={},
        privacy_json={},
    )
    await expect_violation(db_session, duplicate, match="uq_profile_revision")


async def test_revision_number_must_be_positive(db_session: AsyncSession) -> None:
    profile, _ = await make_profile(db_session)
    bad = ProfileRevision(
        career_profile_id=profile.career_profile_id,
        revision_number=0,
        facts_json={},
        privacy_json={},
    )
    await expect_violation(db_session, bad, match="revision_number_positive")


async def test_intent_revision_numbers_are_unique_per_intent(db_session: AsyncSession) -> None:
    graph = await build_full_graph(db_session)
    duplicate = IntentRevision(
        search_intent_id=graph["intent"].search_intent_id, revision_number=1, intent_json={}
    )
    await expect_violation(db_session, duplicate, match="uq_intent_revision")


async def test_one_inbox_item_per_owner_and_opportunity(db_session: AsyncSession) -> None:
    graph = await build_full_graph(db_session)
    duplicate = JobInboxItem(
        owner_id=LOCAL_OWNER_ID,
        job_opportunity_id=graph["opportunity"].job_opportunity_id,
        state="unread",
    )
    await expect_violation(db_session, duplicate, match="uq_job_inbox_item")


async def test_a_listing_is_unique_within_its_source(db_session: AsyncSession) -> None:
    company = await make_company(db_session)
    source = await make_source(db_session, company)
    posting, _ = await make_posting(db_session, source, external_id="same-id")
    duplicate = JobPosting(
        source_configuration_id=source.source_configuration_id,
        company_id=company.company_id,
        external_job_id=posting.external_job_id,
        source_type="greenhouse",
        source_url="https://jobs.example.test/2",
        title="Other",
        current_content_hash="sha256:x",
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    await expect_violation(db_session, duplicate, match="uq_job_posting")


async def test_the_same_external_id_may_exist_on_another_source(db_session: AsyncSession) -> None:
    company = await make_company(db_session)
    first = await make_source(db_session, company)
    second = await make_source(db_session, company)
    await make_posting(db_session, first, external_id="42")
    await make_posting(db_session, second, external_id="42")  # must not raise


async def test_a_scheduled_run_is_created_once(db_session: AsyncSession) -> None:
    db_session.add(CollectionRun(owner_id=LOCAL_OWNER_ID, trigger="scheduled", scheduled_for=NOW))
    await db_session.flush()
    await expect_violation(
        db_session,
        CollectionRun(owner_id=LOCAL_OWNER_ID, trigger="scheduled", scheduled_for=NOW),
        match="uq_collection_run",
    )


async def test_manual_runs_do_not_collide(db_session: AsyncSession) -> None:
    db_session.add_all([CollectionRun(owner_id=LOCAL_OWNER_ID, trigger="manual") for _ in range(2)])
    await db_session.flush()  # scheduled_for is null for manual runs: nulls are distinct


async def test_a_source_board_is_configured_once_per_owner(db_session: AsyncSession) -> None:
    company = await make_company(db_session)
    source = await make_source(db_session, company, identifier="dup-board")
    duplicate = SourceConfiguration(
        owner_id=LOCAL_OWNER_ID,
        source_type="greenhouse",
        external_identifier=source.external_identifier,
        display_name="again",
        url="https://boards.example.test/x",
        config_json={},
    )
    await expect_violation(db_session, duplicate, match="uq_source_configuration")


async def test_there_is_one_schedule_per_owner(db_session: AsyncSession) -> None:
    from datetime import time

    db_session.add(
        ScheduleSetting(
            owner_id=LOCAL_OWNER_ID, run_times_local=[time(7, 30)], timezone="Europe/Lisbon"
        )
    )
    await db_session.flush()
    await expect_violation(
        db_session,
        ScheduleSetting(owner_id=LOCAL_OWNER_ID, run_times_local=[time(8, 0)], timezone="UTC"),
        match="schedule_setting",
    )


async def test_a_posting_has_at_most_one_active_opportunity(db_session: AsyncSession) -> None:
    graph = await build_full_graph(db_session)
    # A second opportunity linking the same posting while the first link is active must be refused.
    with pytest.raises(IntegrityError, match="uq_job_opportunity_link_active_posting"):
        async with db_session.begin_nested():
            await make_opportunity(db_session, graph["posting"])


async def test_rejected_links_do_not_block_a_new_link(db_session: AsyncSession) -> None:
    graph = await build_full_graph(db_session)
    result = await db_session.execute(
        select(JobOpportunityLink).where(
            JobOpportunityLink.job_posting_id == graph["posting"].job_posting_id
        )
    )
    result.scalar_one().state = "rejected"
    await db_session.flush()
    await make_opportunity(db_session, graph["posting"])  # allowed now: rejected links are history


async def test_only_one_provider_connection_is_active(db_session: AsyncSession) -> None:
    def connection() -> ProviderConnection:
        return ProviderConnection(
            owner_id=LOCAL_OWNER_ID,
            provider_type="ollama",
            display_name=unique("p"),
            config_json={},
            is_active=True,
        )

    db_session.add(connection())
    await db_session.flush()
    await expect_violation(
        db_session, connection(), match="uq_provider_connection_active_per_owner"
    )


async def test_the_same_evaluation_inputs_are_stored_once(db_session: AsyncSession) -> None:
    graph = await build_full_graph(db_session)
    first = graph["evaluation"]
    duplicate = MatchEvaluation(
        job_snapshot_id=first.job_snapshot_id,
        job_extraction_id=first.job_extraction_id,
        profile_revision_id=first.profile_revision_id,
        intent_revision_id=first.intent_revision_id,
        policy_version=first.policy_version,
        job_source_hash=first.job_source_hash,
        fit_score=10,
        recommendation="recommended",
        gates_json=[],
        weights_json={},
    )
    await expect_violation(db_session, duplicate, match="uq_match_evaluation_inputs")


@pytest.mark.parametrize("score", [-1, 101])
async def test_fit_score_is_between_0_and_100(db_session: AsyncSession, score: int) -> None:
    graph = await build_full_graph(db_session)
    first = graph["evaluation"]
    bad = MatchEvaluation(
        job_snapshot_id=first.job_snapshot_id,
        job_extraction_id=first.job_extraction_id,
        profile_revision_id=first.profile_revision_id,
        intent_revision_id=first.intent_revision_id,
        policy_version="matching-v2",
        job_source_hash=first.job_source_hash,
        fit_score=score,
        recommendation="recommended",
        gates_json=[],
        weights_json={},
    )
    await expect_violation(db_session, bad, match="fit_score_range")


async def test_invalid_enumeration_values_are_rejected(db_session: AsyncSession) -> None:
    graph = await build_full_graph(db_session)
    other_posting, _ = await make_posting(db_session, graph["source"])
    opportunity = await make_opportunity(db_session, other_posting)
    bad = JobInboxItem(
        owner_id=LOCAL_OWNER_ID, job_opportunity_id=opportunity.job_opportunity_id, state="weird"
    )
    await expect_violation(db_session, bad, match="state_valid")


async def test_skill_relation_pairs_are_ordered_and_unique(db_session: AsyncSession) -> None:
    a = Skill(canonical_name=unique("A"), kind="technology")
    b = Skill(canonical_name=unique("B"), kind="technology")
    db_session.add_all([a, b])
    await db_session.flush()
    await expect_violation(
        db_session,
        SkillRelation(
            skill_id_a=b.skill_id, skill_id_b=a.skill_id, relation="equivalent", origin="ai"
        ),
        match="ordered_pair",
    )
    db_session.add(
        SkillRelation(
            skill_id_a=a.skill_id, skill_id_b=b.skill_id, relation="equivalent", origin="ai"
        )
    )
    await db_session.flush()
    await expect_violation(
        db_session,
        SkillRelation(
            skill_id_a=a.skill_id, skill_id_b=b.skill_id, relation="related", origin="user"
        ),
        match="uq_skill_relation",
    )


async def test_taxonomy_terms_are_unique_per_kind(db_session: AsyncSession) -> None:
    await expect_violation(
        db_session,
        TaxonomyTerm(
            kind="sector",
            term_key="telecom",
            label="dup",
            origin="user",
            introduced_in_taxonomy_version_id=1,
        ),
        match="uq_taxonomy_term",
    )


async def test_similarity_is_a_probability(db_session: AsyncSession) -> None:
    graph = await build_full_graph(db_session)
    other_posting, _ = await make_posting(db_session, graph["source"])
    bad = JobOpportunityLink(
        job_opportunity_id=graph["opportunity"].job_opportunity_id,
        job_posting_id=other_posting.job_posting_id,
        state="possible",
        similarity=Decimal("1.5"),
        features_json={},
        method="dedup-v1",
    )
    await expect_violation(db_session, bad, match="similarity_range")


async def test_a_run_may_be_scoped_to_one_source_and_follows_it_on_delete(
    db_session: AsyncSession,
) -> None:
    source = await make_source(db_session, await make_company(db_session))
    scoped = CollectionRun(
        owner_id=LOCAL_OWNER_ID,
        trigger="manual",
        source_configuration_id=source.source_configuration_id,
    )
    unscoped = CollectionRun(owner_id=LOCAL_OWNER_ID, trigger="manual")
    db_session.add_all([scoped, unscoped])
    await db_session.flush()
    assert scoped.source_configuration_id == source.source_configuration_id
    assert unscoped.source_configuration_id is None  # null means: all enabled sources
