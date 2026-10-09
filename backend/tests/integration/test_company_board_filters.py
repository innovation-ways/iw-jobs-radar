"""Filters on company boards: opt-in, applied before storage (ADR-051)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import make_company, make_intent, make_profile, make_source
from tests.fake_adapter import FakeAdapter, listing, make_posting

from jobs_radar.db.models import JobPosting, SearchIntent, SourceConfiguration, SourceRunResult
from jobs_radar.domain.enums import LOCAL_OWNER_ID, SourceOutcome, SourceType
from jobs_radar.services.collection import CollectionService

pytestmark = pytest.mark.integration

T0 = datetime(2026, 10, 9, 7, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
async def _intent(db_session: AsyncSession) -> None:
    await db_session.execute(update(SearchIntent).values(enabled=False))
    await db_session.execute(update(SourceConfiguration).values(enabled=False))
    profile, _ = await make_profile(db_session)
    intent, _ = await make_intent(db_session, profile)
    intent.enabled = True
    await db_session.flush()


def build(session: AsyncSession, monkeypatch: pytest.MonkeyPatch, adapter: FakeAdapter):
    monkeypatch.setattr(session, "commit", session.flush)

    @asynccontextmanager
    async def same() -> AsyncIterator[AsyncSession]:
        yield session

    return CollectionService(same, {SourceType.GREENHOUSE: adapter}, clock=lambda: T0)  # type: ignore[arg-type]


async def collect(
    session, monkeypatch, adapter, config
) -> tuple[list[JobPosting], SourceRunResult]:
    source = await make_source(session, await make_company(session))
    source.config_json = config
    await session.flush()
    service = build(session, monkeypatch, adapter)
    run = await service.request_run(
        LOCAL_OWNER_ID, source_configuration_id=source.source_configuration_id
    )
    await service.execute_run(run.collection_run_id)
    postings = list(
        (
            await session.execute(
                select(JobPosting)
                .where(JobPosting.source_configuration_id == source.source_configuration_id)
                .order_by(JobPosting.external_job_id)
            )
        ).scalars()
    )
    result = (
        await session.execute(
            select(SourceRunResult).where(
                SourceRunResult.source_configuration_id == source.source_configuration_id
            )
        )
    ).scalar_one()
    return postings, result


def three_postings() -> FakeAdapter:
    return FakeAdapter(
        [
            listing(
                make_posting("1", title="Senior Backend Engineer", locations=("Remote - EU",)),
                make_posting("2", title="Account Executive", locations=("Remote - EU",)),
                make_posting("3", title="Data Engineer", locations=("Berlin, Germany",)),
            )
        ]
    )


async def test_a_board_without_filters_keeps_everything(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    postings, result = await collect(db_session, monkeypatch, three_postings(), {})
    assert [p.external_job_id for p in postings] == ["1", "2", "3"]
    assert result.dropped_count == 0


async def test_a_board_with_filters_stores_only_matching_postings(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = {"schema_version": 1, "categories": ["software", "data"]}
    postings, result = await collect(db_session, monkeypatch, three_postings(), config)
    # The sales role is outside the areas, the Berlin job is outside the owner's reach.
    assert [p.external_job_id for p in postings] == ["1"]
    assert (result.collected_count, result.dropped_count) == (1, 2)
    assert result.outcome == SourceOutcome.SUCCESS.value


async def test_the_limit_makes_a_filtered_run_partial(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = FakeAdapter(
        [
            listing(
                make_posting("1", title="Backend Engineer", locations=("Remote - EU",)),
                make_posting("2", title="Data Engineer", locations=("Remote - EU",)),
            )
        ]
    )
    config = {"schema_version": 1, "categories": ["software", "data"], "max_postings_per_run": 1}
    postings, result = await collect(db_session, monkeypatch, adapter, config)
    assert len(postings) == 1
    assert result.outcome == SourceOutcome.PARTIAL.value
