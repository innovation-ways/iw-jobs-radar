# Backup and restore runbook

A backup is a folder under `backups/` (git-ignored) named `backup-YYYYMMDD-HHMMSS` with:

| File | Content |
|---|---|
| `database.dump` | `pg_dump -Fc` of the whole database (profiles, revisions, jobs, inbox, encrypted credentials). |
| `manifest.json` | database name, migration version, size and SHA-256 of the dump. |
| `credential_key.txt` | the credential key, as a **separate** private file (mode 600). |

The dump holds credentials only in encrypted form. **Keep the key apart from the dump** when you
copy a backup anywhere (for example the dump on a backup disk, the key in a password manager);
together they open the credentials, separately they do not.

## Make a backup

```bash
make backup          # or ./jobs-radar.sh --backup
make backup-list
```

Do this before upgrades, before `--nuclear-reset` and on a regular schedule you choose. The
`backups/` folder is on the same machine: copy it to another disk or machine yourself.

## Prove it works (restore drill)

```bash
make restore-drill   # or ./jobs-radar.sh --restore-drill
```

The drill takes a fresh backup, restores it into a scratch database, compares the row count of
every table and the migration version, drops the scratch database and prints `PASSED` or the
differences. Tables that the worker writes continuously (heartbeat, run results) can differ by a
few rows if the worker is busy during the drill; repeat it or stop the worker for an exact result.
Run it after changing the schema and before relying on a backup.

## Restore

1. Stop what writes: `./jobs-radar.sh --stop worker` and `--stop api`.
2. `make restore BACKUP=backups/backup-YYYYMMDD-HHMMSS CONFIRM=yes` replaces the current database
   with the backup. The checksum is verified first; a damaged dump is refused.
3. Put the matching key in `.env` as `JOBS_RADAR_CREDENTIAL_KEY` if you are restoring on a new
   machine (the value is in `credential_key.txt`). Without it, saved AI keys and tokens must be
   entered again; nothing else is lost.
4. `./jobs-radar.sh --db-migrate` (if the backup is older than the code), then `--start`.

## What is not in a backup

Original CV files and CV text (never stored by design), the frontend's local preferences (theme,
density), and anything outside the database.
