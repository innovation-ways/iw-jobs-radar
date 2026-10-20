"""An installation with data survives every later migration unchanged (ADR-080: C7 and C8).

``tests/golden/owner_scene_0028.sql`` is a data-only dump of a synthetic installation at the schema of
revision ``0028`` (one row in every append-only table, the seed data, a profile, an intent, a job with
its extraction, evaluation and inbox item). The test builds that schema, loads the dump, takes a
fingerprint of every table, upgrades to ``head`` and takes the fingerprints again. A migration may add
tables, columns and rows to the tables listed as additive; it may not change or lose anything else.

The scene is pinned to revision ``0028`` and must not be regenerated once the schema moves on. It was
produced with ``UPDATE_GOLDEN=1 pytest -k regenerate_the_owner_scene`` when ``head`` was ``0028``.
"""

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker
from testcontainers.community.postgres import PostgresContainer
from tests.factories import build_full_graph
from tests.golden import GOLDEN_DIR

from jobs_radar.core.settings import Settings, get_settings
from jobs_radar.db.session import build_engine

pytestmark = pytest.mark.integration

BACKEND_ROOT = Path(__file__).resolve().parents[2]
BASELINE = "0028"
SCENE = GOLDEN_DIR / f"owner_scene_{BASELINE}.sql"
SCRATCH_DB = "jobs_radar_scene_test"

# Tables that later migrations may add rows to (new vocabulary versions and terms). Only the rows that
# existed at the baseline are compared, by primary key. Anything else must be byte-identical.
ADDITIVE = {
    "taxonomy_version": "taxonomy_version_id",
    "taxonomy_term": "taxonomy_term_id",
}
# Tables whose content a migration may legitimately rewrite. Empty on purpose: adding a table here
# needs a reason that the owner has reviewed.
MAY_BE_REWRITTEN: frozenset[str] = frozenset()


def _config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


@pytest.fixture
def scratch(settings: Settings) -> Iterator[str]:
    """An empty database next to the test one, with the settings pointed at it."""
    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
        connection.execute(text(f"CREATE DATABASE {SCRATCH_DB}"))
    previous = os.environ["JOBS_RADAR_DB_NAME"]
    os.environ["JOBS_RADAR_DB_NAME"] = SCRATCH_DB
    get_settings.cache_clear()
    try:
        yield SCRATCH_DB
    finally:
        os.environ["JOBS_RADAR_DB_NAME"] = previous
        get_settings.cache_clear()
        with admin.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)"))
        admin.dispose()


def _tables(connection: Connection) -> dict[str, list[str]]:
    """Every table (except Alembic's) with its columns in table order."""
    rows = connection.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name <> 'alembic_version' "
            "ORDER BY table_name, ordinal_position"
        )
    )
    tables: dict[str, list[str]] = {}
    for table, column in rows:
        tables.setdefault(table, []).append(column)
    return tables


def _fingerprint(
    connection: Connection,
    columns: dict[str, list[str]],
    limits: dict[str, int] | None = None,
) -> dict[str, tuple[int, str]]:
    """Row count and content hash per table, over the given columns only.

    ``limits`` restricts an additive table to the rows whose key is at most the given value.
    """
    result: dict[str, tuple[int, str]] = {}
    for table, names in columns.items():
        selected = ", ".join(f'"{name}"' for name in names)
        where = ""
        if limits and table in limits:
            where = f' WHERE "{ADDITIVE[table]}" <= {limits[table]}'
        # Identifiers come from information_schema and the constants above, never from input.
        query = (
            "SELECT count(*), coalesce(md5(string_agg(r::text, '|' ORDER BY r::text)), '') "  # noqa: S608
            f'FROM (SELECT {selected} FROM "{table}"{where}) r'
        )
        row = connection.execute(text(query)).one()
        result[table] = (row[0], row[1])
    return result


def _load_scene(connection: Connection) -> None:
    """Replace the content of every table with the dump (the dump includes the seed data)."""
    names = ", ".join(f'"{table}"' for table in _tables(connection))
    connection.exec_driver_sql(f"TRUNCATE {names} RESTART IDENTITY CASCADE")
    connection.exec_driver_sql(SCENE.read_text(encoding="utf-8"))
    # The dump empties the search path for the session; give it back before anything else runs.
    connection.exec_driver_sql("SET search_path TO public")


def test_regenerate_the_owner_scene(
    scratch: str, postgres_container: PostgresContainer, settings: Settings
) -> None:
    """Writes the scene dump when ``UPDATE_GOLDEN=1``; otherwise checks that the dump exists."""
    if os.environ.get("UPDATE_GOLDEN") != "1":
        assert SCENE.exists(), "the owner scene dump is missing; see the module docstring"
        return
    command.upgrade(_config(), BASELINE)

    async def populate() -> None:
        engine = build_engine(get_settings())
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                await build_full_graph(session)
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(populate())
    # stderr is dropped: the warnings about circular foreign keys are expected (--disable-triggers).
    code, output = postgres_container.exec(
        [
            "sh",
            "-c",
            f"pg_dump -U jobs_radar_test -d {SCRATCH_DB} --data-only --column-inserts "
            "--disable-triggers --exclude-table=alembic_version 2>/dev/null",
        ]
    )
    assert code == 0
    # psql meta-commands (\restrict, \unrestrict) cannot be executed through a driver.
    lines = [ln for ln in output.decode("utf-8").splitlines() if not ln.startswith("\\")]
    GOLDEN_DIR.mkdir(exist_ok=True)
    SCENE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_the_scene_has_data_in_the_tables_that_matter(scratch: str) -> None:
    """Guards the dump: an empty scene would make the upgrade test meaningless."""
    command.upgrade(_config(), BASELINE)
    engine = create_engine(get_settings().database_url)
    with engine.begin() as connection:
        _load_scene(connection)
        for table in (
            "profile_revision",
            "intent_revision",
            "job_snapshot",
            "job_extraction",
            "match_evaluation",
            "score_dimension",
            "inbox_event",
            "job_inbox_item",
            "taxonomy_term",
        ):
            query = f'SELECT count(*) FROM "{table}"'  # noqa: S608  # fixed names above
            count = connection.execute(text(query)).scalar_one()
            assert count >= 1, table
    engine.dispose()


def test_c7_c8_upgrade_to_head_keeps_every_baseline_row(scratch: str) -> None:
    """Fingerprints of all baseline tables and columns are equal before and after the upgrade."""
    command.upgrade(_config(), BASELINE)
    engine = create_engine(get_settings().database_url)
    with engine.begin() as connection:
        _load_scene(connection)
        columns = _tables(connection)
        limits = {
            table: connection.execute(
                text(f'SELECT coalesce(max("{key}"), 0) FROM "{table}"')  # noqa: S608
            ).scalar_one()
            for table, key in ADDITIVE.items()
        }
        before = _fingerprint(connection, columns, limits)

    command.upgrade(_config(), "head")

    with engine.begin() as connection:
        after = _fingerprint(connection, columns, limits)
    engine.dispose()

    changed = sorted(
        table for table in before if before[table] != after[table] and table not in MAY_BE_REWRITTEN
    )
    assert changed == [], f"a migration changed or lost rows of: {changed}"


def test_the_fingerprint_notices_a_change(scratch: str) -> None:
    """A fingerprint that never differs would hide a destructive migration."""
    command.upgrade(_config(), BASELINE)
    engine = create_engine(get_settings().database_url)
    with engine.begin() as connection:
        _load_scene(connection)
        columns = _tables(connection)
        before = _fingerprint(connection, columns)
        connection.exec_driver_sql(
            "UPDATE company SET canonical_name = canonical_name || ' (edited)'"
        )
        after = _fingerprint(connection, columns)
    engine.dispose()
    assert before["company"] != after["company"]
    assert before["profile_revision"] == after["profile_revision"]
