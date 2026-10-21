# Install from published images

For people who want to *use* Jobs Radar. To work on the code, see the Development section of the
README. Decision record: ADR-079.

## Requirements

Docker with Compose v2: Docker Engine on Linux, Docker Desktop on Windows or macOS. The images are
published for `linux/amd64` and `linux/arm64` (including Apple Silicon). Nothing else to install.

## Start

Download `docker-compose.release.yml` (or clone the repository), then:

```bash
docker compose -f docker-compose.release.yml up -d
```

Open <http://127.0.0.1:5180>. Stop with `docker compose -f docker-compose.release.yml down` (your
data stays in Docker volumes; `down -v` deletes it).

What runs: PostgreSQL, the API, the worker and the web UI. **Only the web UI is published**, on
`127.0.0.1`; the database and the API are reachable only by the other containers. Version 1 has no
authentication (ADR-009): to open the UI from another computer set `JOBS_RADAR_FRONTEND_BIND=0.0.0.0`
and do it only on a network you trust.

## Settings

All optional; put them in your shell or in a file named `.env` next to the compose file.

| Variable | Default | Meaning |
|---|---|---|
| `JOBS_RADAR_VERSION` | `latest` | Image version. Pin it (for example `1.4.0`) to upgrade on purpose. |
| `JOBS_RADAR_FRONTEND_PORT` | `5180` | Port of the web UI. |
| `JOBS_RADAR_FRONTEND_BIND` | `127.0.0.1` | Address the UI is published on. |
| `JOBS_RADAR_OLLAMA_URL` | `http://host.docker.internal:11434` | Where a local model server is (see below). |
| `JOBS_RADAR_ALLOW_LOCAL_PROVIDERS` | `false` | Force-allow a local model server. Optional: the same switch is in *AI & privacy* (ADR-081). |
| `JOBS_RADAR_EXTRACTION_ENABLED` | `false` | Only seeds the first local connection on a fresh database; you can add it in *AI & privacy* instead. |

## Secrets, and the backup you must make

The first start generates two secrets and keeps them in the `secrets` volume: the key that encrypts
the credentials you store in Jobs Radar (AI provider keys, job-board keys), and the database
password. They are never in an image or in the compose file.

**Save the key somewhere safe.** Without it, stored credentials cannot be recovered (you would enter
them again). Print it with:

```bash
docker compose -f docker-compose.release.yml run --rm --no-deps --entrypoint cat init /secrets/credential_key
```

Deleting the volumes `secrets` and `pgdata` separately breaks the install: a new password does not
open an existing database. Delete both together (`down -v`) or neither.

## Upgrade

```bash
JOBS_RADAR_VERSION=<new version> docker compose -f docker-compose.release.yml pull
JOBS_RADAR_VERSION=<new version> docker compose -f docker-compose.release.yml up -d
```

Database migrations run when the API starts. Back up the database first (see the backup and restore
runbook, which describes the development setup; with the images use
`docker compose -f docker-compose.release.yml exec db pg_dump -U jobs_radar jobs_radar > backup.sql`).

## Local AI (optional)

The default is No AI: jobs are collected and shown as "not evaluated". To use a model server on the
same computer (for example Ollama), no file editing is needed:

1. Start the model server and pull a model (for example `ollama pull qwen3:8b`).
2. Open *AI & privacy*, tick **Allow a model server on this computer**, add a *local* connection,
   test it, choose it for job analysis (and for CV import if you like).

Jobs Radar only calls the server it is configured for (`JOBS_RADAR_OLLAMA_URL`, default
`http://host.docker.internal:11434`, which Docker Desktop on Windows and macOS resolves to the host).
Running the model server and making it reachable from a container is your own environment choice;
a model server that listens beyond this computer is open to that network. Setting
`JOBS_RADAR_ALLOW_LOCAL_PROVIDERS=true` in `.env` does the same as the switch and locks it on.

## Demo

`docker compose -f docker-compose.demo.yml up` starts a self-contained demo with invented data on
<http://127.0.0.1:5181>, with its own volume. It never touches the data of an installed copy.
