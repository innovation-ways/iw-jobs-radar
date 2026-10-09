"""Backup and restore drill on synthetic data in a throw-away database (T8.1)."""

import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.community.postgres import PostgresContainer

from jobs_radar.tools.backup import (
    BackupError,
    DbTarget,
    create_backup,
    restore_backup,
    run_drill,
    verify_backup,
)

pytestmark = pytest.mark.integration

KEY = "synthetic-credential-key-for-the-drill-only="


@pytest.fixture
def target(postgres_container: PostgresContainer) -> DbTarget:
    return DbTarget(
        container=postgres_container.get_wrapped_container().id,
        user=postgres_container.username,
        database=postgres_container.dbname,
    )


def test_a_backup_has_a_dump_a_manifest_and_a_separate_private_key_file(
    tmp_path: Path, target: DbTarget
) -> None:
    folder = create_backup(
        target, tmp_path, credential_key=KEY, now=datetime(2026, 10, 9, 8, 0, tzinfo=UTC)
    )
    assert folder.name == "backup-20261009-080000"
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["database"] == target.database and manifest["alembic_version"]
    assert manifest["has_credential_key"] is True and len(manifest["sha256"]) == 64
    assert KEY not in (folder / "manifest.json").read_text()  # the key is never in the manifest
    assert (folder / "credential_key.txt").read_text().strip() == KEY
    for name in ("database.dump", "credential_key.txt"):
        mode = stat.S_IMODE(os.stat(folder / name).st_mode)
        assert mode == 0o600, name
    assert verify_backup(folder).sha256 == manifest["sha256"]


def test_a_backup_without_a_key_says_so(tmp_path: Path, target: DbTarget) -> None:
    folder = create_backup(
        target, tmp_path, credential_key=None, now=datetime(2026, 10, 9, 8, 1, tzinfo=UTC)
    )
    assert json.loads((folder / "manifest.json").read_text())["has_credential_key"] is False
    assert not (folder / "credential_key.txt").exists()


def test_a_damaged_dump_is_detected_before_any_restore(tmp_path: Path, target: DbTarget) -> None:
    folder = create_backup(
        target, tmp_path, credential_key=None, now=datetime(2026, 10, 9, 8, 2, tzinfo=UTC)
    )
    with (folder / "database.dump").open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(BackupError, match="checksum"):
        verify_backup(folder)
    with pytest.raises(BackupError, match="checksum"):
        restore_backup(target, folder, confirmed=True, into="never_created")


def test_restoring_over_a_database_needs_confirmation(tmp_path: Path, target: DbTarget) -> None:
    folder = create_backup(
        target, tmp_path, credential_key=None, now=datetime(2026, 10, 9, 8, 3, tzinfo=UTC)
    )
    with pytest.raises(BackupError, match="confirm"):
        restore_backup(target, folder, confirmed=False)


async def test_the_restore_drill_reproduces_the_data(
    tmp_path: Path, target: DbTarget, db_session: AsyncSession
) -> None:
    # Committed synthetic rows so the dump contains something recognisable.
    await db_session.execute(
        text(
            "INSERT INTO company (canonical_name, name_normalised) VALUES ('Drill Co', 'drill co')"
        )
    )
    await db_session.commit()
    try:
        report = run_drill(
            target, tmp_path, credential_key=KEY, now=datetime(2026, 10, 9, 8, 4, tzinfo=UTC)
        )
        assert report.ok and report.tables_compared > 20
        assert report.mismatches == []
        assert report.alembic_version
        # the scratch database was removed again
        databases = await db_session.execute(text("SELECT datname FROM pg_database"))
        assert report.scratch_database not in {row[0] for row in databases}
    finally:
        await db_session.execute(text("DELETE FROM company WHERE canonical_name = 'Drill Co'"))
        await db_session.commit()
