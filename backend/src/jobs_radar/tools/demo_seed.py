"""Build the fictional demo database (make demo-seed): migrations, then the demo world.

The demo lives in its own database, ``jobs_radar_demo``, next to the real one; the real database is
never read or written. The command refuses any other database name, and anything but the
development environment. With ``--reset`` the demo database is dropped and recreated first.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql

from jobs_radar.core.settings import Settings, get_settings
from jobs_radar.db.session import build_engine, build_session_factory
from jobs_radar.demo.seed import seed_demo

DEMO_DATABASE_SUFFIX = "_demo"
BACKEND_ROOT = Path(__file__).resolve().parents[3]


def check_environment(settings: Settings) -> None:
    """Refuse to seed anything but the development environment's ``*_demo`` database."""
    if settings.env != "dev" or settings.db_name != f"jobs_radar{DEMO_DATABASE_SUFFIX}":
        msg = (
            "Refusing to seed: the demo needs JOBS_RADAR_ENV=dev and "
            f"JOBS_RADAR_DB_NAME=jobs_radar{DEMO_DATABASE_SUFFIX} "
            f"(got '{settings.env}' and '{settings.db_name}')."
        )
        raise SystemExit(msg)


def _create_database(settings: Settings, *, reset: bool) -> None:
    """Create the demo database if it is missing (dropping it first with ``reset``)."""
    # The maintenance database is the one place a database can be created or dropped from.
    with psycopg.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password.get_secret_value(),
        dbname="postgres",
        autocommit=True,
    ) as connection:
        name = sql.Identifier(settings.db_name)
        if reset:
            connection.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (settings.db_name,)
        ).fetchone()
        if exists is None:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(name))


def _migrate() -> None:
    """Apply every Alembic migration to the demo database (settings come from the environment)."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head")


async def _run(reset: bool) -> int:
    settings = get_settings()
    check_environment(settings)
    _create_database(settings, reset=reset)
    _migrate()
    engine = build_engine(settings)
    try:
        report = await seed_demo(build_session_factory(engine), settings)
    finally:
        await engine.dispose()
    print(  # CLI output
        f"Demo ready in '{settings.db_name}': {report.sources} sources, {report.postings} "
        f"postings, {report.inbox_items} inbox items ({report.evaluated} scored)."
    )
    return 0


def main() -> int:
    """Entry point for ``python -m jobs_radar.tools.demo_seed``."""
    parser = argparse.ArgumentParser(description="Build the fictional demo database.")
    parser.add_argument(
        "--reset", action="store_true", help="drop and recreate the demo database first"
    )
    return asyncio.run(_run(parser.parse_args().reset))


if __name__ == "__main__":
    sys.exit(main())
