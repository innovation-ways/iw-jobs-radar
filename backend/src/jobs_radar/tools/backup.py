"""Backup, restore and restore drill of the database and the credential key (T8.1).

A backup is a folder with ``database.dump`` (``pg_dump -Fc``), ``manifest.json`` (database name,
migration version, SHA-256 of the dump) and, when a key is given, ``credential_key.txt`` as a
**separate** file: the encrypted credentials in the dump cannot be read without that key, so keep
the two apart when you copy a backup anywhere. Files are private (mode 600). Restoring over a
database needs explicit confirmation and a verified checksum; the drill restores into a scratch
database and compares every table's row count, so a backup is proven before it is needed.

Commands (run from ``backend/``; see the Makefile)::

    python -m jobs_radar.tools.backup backup  [--dir DIR]
    python -m jobs_radar.tools.backup drill   [--dir DIR]
    python -m jobs_radar.tools.backup restore BACKUP_FOLDER --yes
    python -m jobs_radar.tools.backup list    [--dir DIR]
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

DUMP = "database.dump"
MANIFEST = "manifest.json"
KEY_FILE = "credential_key.txt"
_NAME = re.compile(r"^[A-Za-z0-9_]{1,60}$")


class BackupError(Exception):
    """A backup operation failed; the message is safe to show."""


@dataclass(frozen=True)
class DbTarget:
    """Where the database runs: a container, a role and a database name."""

    container: str
    user: str
    database: str


@dataclass(frozen=True)
class Manifest:
    """What a backup folder says about itself."""

    created_at: str
    database: str
    alembic_version: str
    sha256: str
    size_bytes: int
    has_credential_key: bool


@dataclass
class DrillReport:
    """Outcome of a restore drill."""

    backup: Path
    scratch_database: str
    alembic_version: str
    tables_compared: int = 0
    mismatches: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether every table has the same number of rows after the restore."""
        return self.tables_compared > 0 and not self.mismatches


# --- docker helpers ----------------------------------------------------------------------------


def _docker() -> str:
    path = shutil.which("docker")
    if path is None:
        msg = "docker was not found on PATH."
        raise BackupError(msg)
    return path


def _exec(
    target: DbTarget,
    command: list[str],
    *,
    stdin: Path | None = None,
    stdout: Path | None = None,
) -> str:
    """Run ``command`` inside the database container; return its text output."""
    argv = [_docker(), "exec", *(["-i"] if stdin else []), target.container, *command]
    source = stdin.open("rb") if stdin else None
    sink = stdout.open("wb") if stdout else None
    try:
        # Fixed argument list, no shell: nothing the user typed reaches a shell.
        result = subprocess.run(  # noqa: S603
            argv, stdin=source, stdout=sink or subprocess.PIPE, stderr=subprocess.PIPE, check=False
        )
    finally:
        if source:
            source.close()
        if sink:
            sink.close()
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip().splitlines()[-1:] or ["failed"]
        msg = f"{command[0]} failed: {detail[0]}"
        raise BackupError(msg)
    return "" if stdout else result.stdout.decode()


def _psql(target: DbTarget, database: str, sql: str) -> str:
    return _exec(target, ["psql", "-U", target.user, "-d", database, "-tA", "-c", sql]).strip()


def _valid(name: str) -> str:
    if not _NAME.match(name):
        msg = f"'{name}' is not a valid database name."
        raise BackupError(msg)
    return name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _private_write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


# --- operations --------------------------------------------------------------------------------


def create_backup(
    target: DbTarget, directory: Path, *, credential_key: str | None, now: datetime | None = None
) -> Path:
    """Dump the database into a new timestamped folder under ``directory``; return the folder."""
    moment = now or datetime.now(UTC)
    folder = directory / f"backup-{moment:%Y%m%d-%H%M%S}"
    folder.mkdir(parents=True, exist_ok=False, mode=0o700)
    dump = folder / DUMP
    _exec(target, ["pg_dump", "-Fc", "-U", target.user, "-d", target.database], stdout=dump)
    dump.chmod(0o600)
    manifest = Manifest(
        created_at=moment.isoformat(),
        database=target.database,
        alembic_version=_psql(target, target.database, "SELECT version_num FROM alembic_version"),
        sha256=_sha256(dump),
        size_bytes=dump.stat().st_size,
        has_credential_key=bool(credential_key),
    )
    _private_write(folder / MANIFEST, json.dumps(manifest.__dict__, indent=2))
    if credential_key:
        _private_write(folder / KEY_FILE, credential_key + "\n")
    return folder


def verify_backup(folder: Path) -> Manifest:
    """Read the manifest and check the dump against its checksum."""
    try:
        manifest = Manifest(**json.loads((folder / MANIFEST).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as error:
        msg = f"{folder} is not a readable backup."
        raise BackupError(msg) from error
    if not (folder / DUMP).is_file() or _sha256(folder / DUMP) != manifest.sha256:
        msg = "The dump does not match its checksum; the backup is damaged."
        raise BackupError(msg)
    return manifest


def restore_backup(
    target: DbTarget, folder: Path, *, confirmed: bool, into: str | None = None
) -> Manifest:
    """Restore a verified backup, over the target database or into a new ``into`` database."""
    manifest = verify_backup(folder)
    destination = _valid(into) if into else target.database
    if destination == target.database and not confirmed:
        msg = "Restoring replaces the current database: confirm it explicitly (--yes)."
        raise BackupError(msg)
    flags = ["--no-owner"]
    if destination == target.database:
        flags += ["--clean", "--if-exists"]
    else:
        _psql(target, "postgres", f'DROP DATABASE IF EXISTS "{destination}"')
        _psql(target, "postgres", f'CREATE DATABASE "{destination}"')
    _exec(
        target,
        ["pg_restore", *flags, "-U", target.user, "-d", destination],
        stdin=folder / DUMP,
    )
    return manifest


def _row_counts(target: DbTarget, database: str) -> dict[str, int]:
    tables = _psql(
        target, database, "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"
    ).splitlines()
    return {
        # The table name comes from pg_tables and is validated, never from user input.
        table: int(_psql(target, database, f'SELECT count(*) FROM public."{_valid(table)}"'))  # noqa: S608  # nosec B608
        for table in tables
        if table
    }


def run_drill(
    target: DbTarget, directory: Path, *, credential_key: str | None, now: datetime | None = None
) -> DrillReport:
    """Back up, restore into a scratch database, compare row counts, drop the scratch database."""
    moment = now or datetime.now(UTC)
    folder = create_backup(target, directory, credential_key=credential_key, now=moment)
    scratch = f"{target.database}_drill_{moment:%H%M%S}"[:60]
    manifest = verify_backup(folder)
    report = DrillReport(folder, scratch, manifest.alembic_version)
    try:
        restore_backup(target, folder, confirmed=False, into=scratch)
        before, after = _row_counts(target, target.database), _row_counts(target, scratch)
        report.tables_compared = len(before)
        for table, count in before.items():
            if after.get(table) != count:
                report.mismatches.append(f"{table}: {count} -> {after.get(table)}")
        if (
            _psql(target, scratch, "SELECT version_num FROM alembic_version")
            != manifest.alembic_version
        ):
            report.mismatches.append("alembic_version differs")
    finally:
        _psql(target, "postgres", f'DROP DATABASE IF EXISTS "{scratch}"')
    return report


# --- command line ------------------------------------------------------------------------------


def _resolve_target() -> tuple[DbTarget, str | None]:
    from jobs_radar.core.settings import get_settings  # lazy: only the CLI needs settings

    settings = get_settings()
    compose = subprocess.run(  # noqa: S603
        [_docker(), "compose", "ps", "-q", "db"],
        capture_output=True,
        text=True,
        check=False,
        cwd=Path(__file__).resolve().parents[4],
    )
    container = compose.stdout.strip()
    if not container:
        msg = "The database container is not running (./jobs-radar.sh --status)."
        raise BackupError(msg)
    key = settings.credential_key.get_secret_value() if settings.credential_key else None
    return DbTarget(container, settings.db_user, settings.db_name), key


def main(argv: list[str] | None = None) -> int:
    """Entry point of ``python -m jobs_radar.tools.backup``."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("command", choices=["backup", "drill", "restore", "list"])
    parser.add_argument("folder", nargs="?", help="backup folder (restore)")
    parser.add_argument("--dir", default="../backups", help="where backups are kept")
    parser.add_argument("--yes", action="store_true", help="confirm replacing the database")
    args = parser.parse_args(argv)
    directory = Path(args.dir)
    try:
        if args.command == "list":
            for folder in sorted(directory.glob("backup-*")):
                manifest = verify_backup(folder)
                size, version = manifest.size_bytes, manifest.alembic_version
                print(f"{folder.name}  {size} bytes  migration {version}")
            return 0
        target, key = _resolve_target()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if args.command == "backup":
            folder = create_backup(target, directory, credential_key=key)
            print(f"Backup written to {folder} (the credential key is a separate file there).")
            return 0
        if args.command == "drill":
            report = run_drill(target, directory, credential_key=key)
            print(
                f"Restore drill of {report.backup.name}: {report.tables_compared} tables compared"
            )
            for line in report.mismatches:
                print(f"  MISMATCH {line}")
            print("PASSED" if report.ok else "FAILED")
            return 0 if report.ok else 1
        if not args.folder:
            parser.error("restore needs the backup folder")
        restore_backup(target, Path(args.folder), confirmed=args.yes)
        print("Restored. Restart the api and worker (./jobs-radar.sh --restart).")
        return 0
    except BackupError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
