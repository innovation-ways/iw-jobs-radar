"""Integration tests for the baseline schema, identity keys and append-only triggers (ADR-030)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.triggers import create_append_only_trigger

pytestmark = pytest.mark.integration


async def test_baseline_table_exists(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text("SELECT to_regclass('public.worker_heartbeat') IS NOT NULL")
    )
    assert result.scalar_one() is True


async def test_primary_key_is_identity_named_after_the_table(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT data_type, identity_generation FROM information_schema.columns "
            "WHERE table_name = 'worker_heartbeat' AND column_name = 'worker_heartbeat_id'"
        )
    )
    data_type, generation = result.one()
    assert data_type == "bigint"
    assert generation == "BY DEFAULT"


async def test_every_column_is_documented(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT c.column_name FROM information_schema.columns c "
            "LEFT JOIN pg_catalog.pg_statio_all_tables st "
            "  ON st.schemaname = c.table_schema AND st.relname = c.table_name "
            "WHERE c.table_schema = 'public' AND c.table_name <> 'alembic_version' "
            "AND col_description(st.relid, c.ordinal_position) IS NULL"
        )
    )
    assert result.scalars().all() == []


async def test_append_only_trigger_blocks_update_and_delete(db_session: AsyncSession) -> None:
    await db_session.execute(
        text("CREATE TABLE tmp_event (tmp_event_id bigint PRIMARY KEY, note text)")
    )
    await db_session.execute(text(create_append_only_trigger("tmp_event")))
    await db_session.execute(text("INSERT INTO tmp_event VALUES (1, 'a')"))
    await db_session.commit()
    try:
        with pytest.raises(DBAPIError, match="append-only"):
            await db_session.execute(text("UPDATE tmp_event SET note = 'b'"))
        await db_session.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            await db_session.execute(text("DELETE FROM tmp_event"))
        await db_session.rollback()
    finally:
        await db_session.execute(text("DROP TABLE tmp_event"))
        await db_session.commit()


async def test_audited_procedure_can_bypass_the_trigger(db_session: AsyncSession) -> None:
    await db_session.execute(
        text("CREATE TABLE tmp_event2 (tmp_event2_id bigint PRIMARY KEY, note text)")
    )
    await db_session.execute(text(create_append_only_trigger("tmp_event2")))
    await db_session.execute(text("INSERT INTO tmp_event2 VALUES (1, 'a')"))
    await db_session.commit()
    try:
        await db_session.execute(text("SET LOCAL jobs_radar.allow_mutation = 'on'"))
        await db_session.execute(text("DELETE FROM tmp_event2"))
        await db_session.commit()
        remaining = await db_session.execute(text("SELECT count(*) FROM tmp_event2"))
        assert remaining.scalar_one() == 0
    finally:
        await db_session.execute(text("DROP TABLE tmp_event2"))
        await db_session.commit()
