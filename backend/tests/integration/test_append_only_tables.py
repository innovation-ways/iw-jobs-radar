"""Immutable tables reject UPDATE and DELETE; the audited procedure is the only bypass (ADR-030)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import (
    build_full_graph,
    make_company,
    make_extraction,
    make_posting,
    make_source,
)

from jobs_radar.db.triggers import APPEND_ONLY_TABLES, CONDITIONALLY_IMMUTABLE_TABLES

pytestmark = pytest.mark.integration


def test_the_list_of_immutable_tables_matches_the_design() -> None:
    assert set(APPEND_ONLY_TABLES) == {
        "profile_revision",
        "intent_revision",
        "evidence",
        "job_snapshot",
        "job_change_event",
        "match_evaluation",
        "score_dimension",
        "inbox_event",
        "source_run_result",
        "audit_event",
    }
    assert CONDITIONALLY_IMMUTABLE_TABLES == ("job_extraction",)


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
async def test_update_and_delete_are_rejected(db_session: AsyncSession, table: str) -> None:
    await build_full_graph(db_session)
    # A no-op UPDATE still fires the trigger, which is exactly what must be blocked.
    first_column = (
        await db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = :t ORDER BY ordinal_position LIMIT 1"
            ),
            {"t": table},
        )
    ).scalar_one()
    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(text(f"UPDATE {table} SET {first_column} = {first_column}"))  # noqa: S608
    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(text(f"DELETE FROM {table}"))  # noqa: S608


@pytest.mark.parametrize("table", [*APPEND_ONLY_TABLES, *CONDITIONALLY_IMMUTABLE_TABLES])
async def test_every_immutable_table_has_its_trigger(db_session: AsyncSession, table: str) -> None:
    count = (
        await db_session.execute(
            text(
                "SELECT count(*) FROM pg_trigger WHERE tgrelid = to_regclass(:t) AND NOT tgisinternal"
            ),
            {"t": table},
        )
    ).scalar_one()
    assert count == 1


async def test_a_pending_extraction_may_be_finalised_once(db_session: AsyncSession) -> None:
    company = await make_company(db_session)
    source = await make_source(db_session, company)
    _, snapshot = await make_posting(db_session, source)
    extraction = await make_extraction(db_session, snapshot, status="pending")

    await db_session.execute(
        text(
            "UPDATE job_extraction SET status = 'succeeded', attributes_json = '{}' WHERE job_extraction_id = :i"
        ),
        {"i": extraction.job_extraction_id},
    )
    with pytest.raises(DBAPIError, match="immutable once finalised"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE job_extraction SET model = 'other' WHERE job_extraction_id = :i"),
                {"i": extraction.job_extraction_id},
            )
    with pytest.raises(DBAPIError, match="immutable once finalised"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM job_extraction WHERE job_extraction_id = :i"),
                {"i": extraction.job_extraction_id},
            )


async def test_a_failed_extraction_is_also_final(db_session: AsyncSession) -> None:
    company = await make_company(db_session)
    source = await make_source(db_session, company)
    _, snapshot = await make_posting(db_session, source)
    extraction = await make_extraction(db_session, snapshot, status="pending")
    await db_session.execute(
        text(
            "UPDATE job_extraction SET status = 'failed', error_class = 'timeout' WHERE job_extraction_id = :i"
        ),
        {"i": extraction.job_extraction_id},
    )
    with pytest.raises(DBAPIError, match="immutable once finalised"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE job_extraction SET status = 'succeeded' WHERE job_extraction_id = :i"),
                {"i": extraction.job_extraction_id},
            )
