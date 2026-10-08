"""Postings and immutable snapshots (LLD sections 2 and 7, TR-3)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import NOW, make_company, make_source

from jobs_radar.db.models import JobPosting, JobSnapshot
from jobs_radar.repositories.jobs import JobRepository

pytestmark = pytest.mark.integration


async def count(session: AsyncSession, model: type, **filters: object) -> int:
    statement = select(func.count()).select_from(model)
    for column, value in filters.items():
        statement = statement.where(getattr(model, column) == value)
    return int((await session.execute(statement)).scalar_one())


async def test_upserting_a_new_posting_creates_it(db_session: AsyncSession) -> None:
    source = await make_source(db_session, await make_company(db_session))
    posting_result = await JobRepository(db_session).upsert_posting(
        source,
        external_job_id="100",
        source_url="https://jobs.example.test/100",
        title="Engineer",
        content_hash="sha256:aaa",
        seen_at=NOW,
    )
    posting = posting_result.posting
    created = posting_result.created
    assert created is True
    assert posting.first_seen_at == NOW
    assert posting.last_seen_at == NOW
    assert posting.closed_at is None
    assert posting.company_id == source.company_id
    assert posting.source_type == "greenhouse"


async def test_upserting_again_keeps_one_row_and_refreshes_last_seen(
    db_session: AsyncSession,
) -> None:
    source = await make_source(db_session, await make_company(db_session))
    repository = JobRepository(db_session)
    first_result = await repository.upsert_posting(
        source,
        external_job_id="100",
        source_url="u1",
        title="Engineer",
        content_hash="sha256:aaa",
        seen_at=NOW,
    )
    first = first_result.posting
    later = NOW + timedelta(days=1)
    second_result = await repository.upsert_posting(
        source,
        external_job_id="100",
        source_url="u2",
        title="Senior Engineer",
        content_hash="sha256:bbb",
        seen_at=later,
    )
    second = second_result.posting
    created = second_result.created
    assert created is False
    assert second.job_posting_id == first.job_posting_id
    assert second.first_seen_at == NOW  # never moves
    assert second.last_seen_at == later
    assert second.title == "Senior Engineer"
    assert second.current_content_hash == "sha256:bbb"
    assert (
        await count(db_session, JobPosting, source_configuration_id=source.source_configuration_id)
        == 1
    )


async def test_a_closed_posting_that_reappears_is_reopened(db_session: AsyncSession) -> None:
    source = await make_source(db_session, await make_company(db_session))
    repository = JobRepository(db_session)
    posting_result = await repository.upsert_posting(
        source, external_job_id="7", source_url="u", title="t", content_hash="sha256:a", seen_at=NOW
    )
    posting = posting_result.posting
    posting.closed_at = NOW + timedelta(days=1)
    await db_session.flush()
    again_result = await repository.upsert_posting(
        source,
        external_job_id="7",
        source_url="u",
        title="t",
        content_hash="sha256:a",
        seen_at=NOW + timedelta(days=2),
    )
    again = again_result.posting
    assert again.closed_at is None


async def test_identical_content_does_not_create_a_second_snapshot(
    db_session: AsyncSession,
) -> None:
    source = await make_source(db_session, await make_company(db_session))
    repository = JobRepository(db_session)
    posting_result = await repository.upsert_posting(
        source, external_job_id="1", source_url="u", title="t", content_hash="sha256:a", seen_at=NOW
    )
    posting = posting_result.posting
    first, created_first = await repository.add_snapshot_if_new(
        posting,
        content_hash="sha256:a",
        fetched_at=NOW,
        raw_payload={"a": 1},
        normalised={"title": "t"},
    )
    second, created_second = await repository.add_snapshot_if_new(
        posting,
        content_hash="sha256:a",
        fetched_at=NOW + timedelta(hours=1),
        raw_payload={"a": 1},
        normalised={"title": "t"},
    )
    assert (created_first, created_second) == (True, False)
    assert second.job_snapshot_id == first.job_snapshot_id
    assert await count(db_session, JobSnapshot, job_posting_id=posting.job_posting_id) == 1


async def test_changed_content_adds_a_snapshot_and_latest_returns_the_newest(
    db_session: AsyncSession,
) -> None:
    source = await make_source(db_session, await make_company(db_session))
    repository = JobRepository(db_session)
    posting_result = await repository.upsert_posting(
        source, external_job_id="1", source_url="u", title="t", content_hash="sha256:a", seen_at=NOW
    )
    posting = posting_result.posting
    await repository.add_snapshot_if_new(
        posting, content_hash="sha256:a", fetched_at=NOW, raw_payload={}, normalised={}
    )
    newer, created = await repository.add_snapshot_if_new(
        posting,
        content_hash="sha256:b",
        fetched_at=NOW + timedelta(days=1),
        raw_payload={},
        normalised={},
    )
    assert created is True
    latest = await repository.latest_snapshot(posting.job_posting_id)
    assert latest is not None
    assert latest.job_snapshot_id == newer.job_snapshot_id
    assert await repository.latest_snapshot(987654321) is None


async def test_a_snapshot_keeps_the_payload_exactly(db_session: AsyncSession) -> None:
    source = await make_source(db_session, await make_company(db_session))
    repository = JobRepository(db_session)
    posting_result = await repository.upsert_posting(
        source, external_job_id="1", source_url="u", title="t", content_hash="sha256:a", seen_at=NOW
    )
    posting = posting_result.posting
    raw = {"id": 1, "nested": {"list": [1, 2, 3]}, "text": "naïve café"}
    snapshot, _ = await repository.add_snapshot_if_new(
        posting,
        content_hash="sha256:a",
        fetched_at=datetime(2026, 10, 8, tzinfo=UTC),
        raw_payload=raw,
        normalised={},
    )
    await db_session.refresh(snapshot)
    assert snapshot.raw_payload_json == raw
