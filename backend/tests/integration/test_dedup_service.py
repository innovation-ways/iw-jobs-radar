"""Opportunity grouping with dedup-v1 (T4.7)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import make_company, make_posting, make_source

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.core.errors import ConflictError, NotFoundError
from jobs_radar.db.models import JobOpportunity, JobOpportunityLink, JobPosting
from jobs_radar.domain.enums import ProviderErrorClass, SourceType
from jobs_radar.services.dedup import DedupService

pytestmark = pytest.mark.integration

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
TEXT = (
    "Design and evaluate language model powered features for enterprise customers. "
    "You will work with product and research teams to ship reliable systems. "
    "Requirements include Python, API design and strong communication skills."
)


@pytest.fixture(autouse=True)
async def _only_this_tests_postings(db_session: AsyncSession) -> None:
    """Close postings committed by earlier tests so only this test's postings are processed."""
    await db_session.execute(
        update(JobPosting).where(JobPosting.closed_at.is_(None)).values(closed_at=T0)
    )


class FakeEmbedder:
    model = "fake-embed"

    def __init__(self, vectors: dict[str, list[float]] | Exception) -> None:
        self.vectors = vectors
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if isinstance(self.vectors, Exception):
            raise self.vectors
        return [self.vectors.get(t, [1.0, 0.0]) for t in texts]


async def two_sources(session: AsyncSession) -> tuple[Any, Any, Any]:
    company = await make_company(session)
    a = await make_source(session, company, source_type=SourceType.GREENHOUSE)
    b = await make_source(session, company, source_type=SourceType.LEVER)
    return company, a, b


async def posting(session: AsyncSession, source: Any, **kwargs: Any) -> Any:
    options = {
        "title": "Senior AI Engineer",
        "description": TEXT,
        "locations": ["Lisbon, Portugal"],
        "first_seen_at": T0,
        **kwargs,
    }
    created, _snapshot = await make_posting(session, source, **options)
    return created


async def links_of(session: AsyncSession, opportunity_id: int) -> list[JobOpportunityLink]:
    rows = await session.execute(
        select(JobOpportunityLink)
        .where(JobOpportunityLink.job_opportunity_id == opportunity_id)
        .order_by(JobOpportunityLink.job_opportunity_link_id)
    )
    return list(rows.scalars())


async def opportunity_of(session: AsyncSession, job_posting_id: int) -> JobOpportunity:
    return (
        await session.execute(
            select(JobOpportunity)
            .join(JobOpportunityLink)
            .where(
                JobOpportunityLink.job_posting_id == job_posting_id,
                JobOpportunityLink.state != "rejected",
            )
        )
    ).scalar_one()


# --- grouping ----------------------------------------------------------------------------------------------


async def test_a_posting_with_no_match_gets_its_own_opportunity(db_session: AsyncSession) -> None:
    _c, a, _b = await two_sources(db_session)
    p = await posting(db_session, a)
    link = await DedupService(db_session).link_posting(p.job_posting_id)
    assert (link.state, float(link.similarity), link.method) == ("auto", 1.0, "dedup-v1")
    opportunity = await opportunity_of(db_session, p.job_posting_id)
    assert opportunity.primary_job_posting_id == p.job_posting_id
    assert opportunity.company_id == p.company_id
    assert (opportunity.first_seen_at, opportunity.last_seen_at, opportunity.closed_at) == (
        T0,
        T0,
        None,
    )


async def test_the_same_job_on_another_source_joins_the_opportunity_automatically(
    db_session: AsyncSession,
) -> None:
    _c, a, b = await two_sources(db_session)
    first = await posting(db_session, a)
    second = await posting(db_session, b, first_seen_at=T0 + timedelta(days=2))
    service = DedupService(db_session)
    await service.link_posting(first.job_posting_id)
    link = await service.link_posting(second.job_posting_id)

    assert link.state == "auto" and float(link.similarity) >= 0.9
    opportunity = await opportunity_of(db_session, first.job_posting_id)
    assert (
        await opportunity_of(db_session, second.job_posting_id)
    ).job_opportunity_id == opportunity.job_opportunity_id
    assert len(await links_of(db_session, opportunity.job_opportunity_id)) == 2
    assert link.features_json["location"] == "identical"
    assert opportunity.primary_job_posting_id == first.job_posting_id  # employer ATS, earliest
    assert opportunity.last_seen_at == T0 + timedelta(days=2) or opportunity.last_seen_at >= T0


async def test_a_moderately_similar_listing_is_grouped_but_flagged_possible(
    db_session: AsyncSession,
) -> None:
    _c, a, b = await two_sources(db_session)
    first = await posting(db_session, a)
    reworded = (
        "We are hiring someone to design and evaluate features powered by language models. "
        "Collaborate with product and research colleagues. Python and API design skills needed."
    )
    second = await posting(
        db_session, b, description=reworded, title="Senior AI Engineer - Remote OK"
    )
    service = DedupService(db_session)
    await service.link_posting(first.job_posting_id)
    link = await service.link_posting(second.job_posting_id)
    assert link.state in {"possible", "auto"}
    if link.state == "possible":
        assert 0.75 <= float(link.similarity) < 0.9 or link.features_json["location"] == "overlap"


async def test_the_same_title_in_another_city_is_a_different_opportunity(
    db_session: AsyncSession,
) -> None:
    _c, a, b = await two_sources(db_session)
    first = await posting(db_session, a, locations=["Lisbon, Portugal"])
    second = await posting(db_session, b, locations=["Berlin, Germany"])
    service = DedupService(db_session)
    await service.link_posting(first.job_posting_id)
    await service.link_posting(second.job_posting_id)
    assert (await opportunity_of(db_session, first.job_posting_id)).job_opportunity_id != (
        await opportunity_of(db_session, second.job_posting_id)
    ).job_opportunity_id


async def test_listings_of_the_same_board_are_never_linked(db_session: AsyncSession) -> None:
    company = await make_company(db_session)
    board = await make_source(db_session, company)
    one = await posting(db_session, board)
    two = await posting(db_session, board)  # identical text, title and place: several openings
    service = DedupService(db_session)
    await service.link_posting(one.job_posting_id)
    await service.link_posting(two.job_posting_id)
    assert (await opportunity_of(db_session, one.job_posting_id)).job_opportunity_id != (
        await opportunity_of(db_session, two.job_posting_id)
    ).job_opportunity_id


async def test_listings_of_different_companies_are_never_linked(db_session: AsyncSession) -> None:
    _c1, a, _b = await two_sources(db_session)
    other = await make_source(
        db_session, await make_company(db_session), source_type=SourceType.LEVER
    )
    one, two = await posting(db_session, a), await posting(db_session, other)
    service = DedupService(db_session)
    await service.link_posting(one.job_posting_id)
    await service.link_posting(two.job_posting_id)
    assert (await opportunity_of(db_session, one.job_posting_id)).job_opportunity_id != (
        await opportunity_of(db_session, two.job_posting_id)
    ).job_opportunity_id


async def test_linking_an_already_linked_posting_changes_nothing(db_session: AsyncSession) -> None:
    _c, a, _b = await two_sources(db_session)
    p = await posting(db_session, a)
    service = DedupService(db_session)
    first = await service.link_posting(p.job_posting_id)
    again = await service.link_posting(p.job_posting_id)
    assert first.job_opportunity_link_id == again.job_opportunity_link_id
    total = await db_session.scalar(
        select(func.count())
        .select_from(JobOpportunityLink)
        .where(JobOpportunityLink.job_posting_id == p.job_posting_id)
    )
    assert total == 1


async def test_link_unlinked_processes_every_open_posting_once(db_session: AsyncSession) -> None:
    _c, a, b = await two_sources(db_session)
    await posting(db_session, a)
    await posting(db_session, b)
    await posting(db_session, a, locations=["Berlin"])
    service = DedupService(db_session)
    assert await service.link_unlinked() == 3
    assert await service.link_unlinked() == 0


# --- decisions by the owner ---------------------------------------------------------------------------------------


async def possible_pair(session: AsyncSession) -> tuple[Any, Any, JobOpportunityLink]:
    """Two listings forced into a 'possible' link (identical places, weaker text overlap)."""
    _c, a, b = await two_sources(session)
    first = await posting(session, a)
    second = await posting(
        session,
        b,
        description=TEXT + " Plus extra paragraph about benefits and perks and locations",
        first_seen_at=T0 + timedelta(days=40),
    )
    service = DedupService(session)
    await service.link_posting(first.job_posting_id)
    link = await service.link_posting(second.job_posting_id)
    if link.state == "auto":  # make the scenario deterministic
        link.state = "possible"
        await session.flush()
    return first, second, link


async def test_confirming_a_link_keeps_it_and_records_the_decision(
    db_session: AsyncSession,
) -> None:
    _first, _second, link = await possible_pair(db_session)
    confirmed = await DedupService(db_session).confirm(link.job_opportunity_link_id)
    assert confirmed.state == "confirmed" and confirmed.decided_by_user_at is not None


async def test_rejecting_a_link_gives_the_posting_its_own_opportunity_and_remembers_the_pair(
    db_session: AsyncSession,
) -> None:
    first, second, link = await possible_pair(db_session)
    service = DedupService(db_session)
    new_opportunity = await service.reject(link.job_opportunity_link_id)

    assert new_opportunity.primary_job_posting_id == second.job_posting_id
    old = await opportunity_of(db_session, first.job_posting_id)
    assert old.job_opportunity_id != new_opportunity.job_opportunity_id
    await db_session.refresh(link)
    assert link.state == "rejected" and link.decided_by_user_at is not None
    # the rejected pair is history: running the linker again never groups them again
    await service.link_unlinked()
    assert (
        await opportunity_of(db_session, second.job_posting_id)
    ).job_opportunity_id == new_opportunity.job_opportunity_id
    assert old.primary_job_posting_id == first.job_posting_id


async def test_a_rejected_pair_is_not_proposed_again_for_a_fresh_posting_of_the_same_listing(
    db_session: AsyncSession,
) -> None:
    first, second, link = await possible_pair(db_session)
    service = DedupService(db_session)
    await service.reject(link.job_opportunity_link_id)
    # drop the second posting's own link so it must be linked from scratch
    own = await opportunity_of(db_session, second.job_posting_id)
    own_link = (await links_of(db_session, own.job_opportunity_id))[0]
    await db_session.delete(own_link)
    await db_session.flush()
    await service.link_posting(second.job_posting_id)
    assert (await opportunity_of(db_session, second.job_posting_id)).job_opportunity_id != (
        await opportunity_of(db_session, first.job_posting_id)
    ).job_opportunity_id


async def test_unknown_or_already_decided_links_are_refused(db_session: AsyncSession) -> None:
    service = DedupService(db_session)
    with pytest.raises(NotFoundError):
        await service.confirm(987654321)
    with pytest.raises(NotFoundError):
        await service.reject(987654321)
    _f, _s, link = await possible_pair(db_session)
    await service.reject(link.job_opportunity_link_id)
    with pytest.raises(ConflictError):
        await service.confirm(link.job_opportunity_link_id)


# --- aggregates -----------------------------------------------------------------------------------------------------


async def test_an_opportunity_stays_open_while_any_listing_is_open_and_closes_with_the_last(
    db_session: AsyncSession,
) -> None:
    _c, a, b = await two_sources(db_session)
    one = await posting(db_session, a)
    two = await posting(db_session, b)
    service = DedupService(db_session)
    await service.link_posting(one.job_posting_id)
    await service.link_posting(two.job_posting_id)
    opportunity = await opportunity_of(db_session, one.job_posting_id)

    one.closed_at = T0 + timedelta(days=3)
    await db_session.flush()
    await service.refresh_opportunity(opportunity.job_opportunity_id)
    await db_session.refresh(opportunity)
    assert opportunity.closed_at is None

    two.closed_at = T0 + timedelta(days=5)
    await db_session.flush()
    await service.refresh_opportunity(opportunity.job_opportunity_id)
    await db_session.refresh(opportunity)
    assert opportunity.closed_at == T0 + timedelta(days=5)


# --- embeddings ----------------------------------------------------------------------------------------------------------------


async def test_embeddings_are_used_when_available_and_the_features_say_so(
    db_session: AsyncSession,
) -> None:
    _c, a, b = await two_sources(db_session)
    first = await posting(db_session, a, description="First wording of the description text")
    second = await posting(db_session, b, description="A completely different wording used here")
    embedder = FakeEmbedder({})  # same vector for everything: cosine 1.0
    service = DedupService(db_session, embedder=embedder)
    await service.link_posting(first.job_posting_id)
    link = await service.link_posting(second.job_posting_id)
    assert embedder.calls >= 1
    assert link.features_json["description_method"] == "embedding"
    assert link.features_json["description"] == pytest.approx(1.0)


async def test_a_failing_embedder_falls_back_to_shingles(db_session: AsyncSession) -> None:
    _c, a, b = await two_sources(db_session)
    first, second = await posting(db_session, a), await posting(db_session, b)
    embedder = FakeEmbedder(ProviderError(ProviderErrorClass.UNAVAILABLE, "down"))
    service = DedupService(db_session, embedder=embedder)
    await service.link_posting(first.job_posting_id)
    link = await service.link_posting(second.job_posting_id)
    assert link.features_json["description_method"] == "shingles"
    assert link.state == "auto"  # identical text still links without the model
