#!/bin/sh
# Entrypoint of the backend image (ADR-079).
#
#   docker-entrypoint.sh init      create the secrets once (run by the compose "init" service, as root)
#   docker-entrypoint.sh <command> load the secrets into the environment, then run the command
#
# The secrets live in the directory named by JOBS_RADAR_SECRETS_DIR (a named volume): the key that
# encrypts stored credentials (ADR-033) and the database password. A value already present in the
# environment always wins, so the development flow (.env) is unchanged. Nothing is ever printed.
set -eu

dir="${JOBS_RADAR_SECRETS_DIR:-}"

if [ "${1:-}" = "init" ]; then
  [ -n "$dir" ] || { echo "JOBS_RADAR_SECRETS_DIR is not set" >&2; exit 2; }
  mkdir -p "$dir"
  umask 077
  if [ ! -s "$dir/credential_key" ]; then
    # A Fernet key is 32 random bytes, url-safe base64 encoded.
    python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode(), end='')" \
      > "$dir/credential_key"
    chmod 400 "$dir/credential_key"
  fi
  if [ ! -s "$dir/db_password" ]; then
    python -c "import secrets, string; a = string.ascii_letters + string.digits; print(''.join(secrets.choice(a) for _ in range(32)), end='')" \
      > "$dir/db_password"
    # The database container (another user) reads it; the database is not published.
    chmod 444 "$dir/db_password"
  fi
  # Run as root by the init service: hand the key to the unprivileged user of the image.
  if [ "$(id -u)" = "0" ]; then
    chown "${JOBS_RADAR_SECRETS_OWNER:-10001}" "$dir/credential_key"
  fi
  exit 0
fi

if [ -n "$dir" ]; then
  if [ -z "${JOBS_RADAR_CREDENTIAL_KEY:-}" ] && [ -r "$dir/credential_key" ]; then
    JOBS_RADAR_CREDENTIAL_KEY="$(cat "$dir/credential_key")"
    export JOBS_RADAR_CREDENTIAL_KEY
  fi
  if [ -z "${JOBS_RADAR_DB_PASSWORD:-}" ] && [ -r "$dir/db_password" ]; then
    JOBS_RADAR_DB_PASSWORD="$(cat "$dir/db_password")"
    export JOBS_RADAR_DB_PASSWORD
  fi
fi

exec "$@"
