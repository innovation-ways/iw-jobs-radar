# Operations guide

Jobs Radar runs as PostgreSQL, an API and a worker in Docker, plus the Vite frontend on the host.
Everything is managed by `./jobs-radar.sh` (menu) or its flags; `make help` lists the same actions.

## First start

1. Install Docker, `uv` and Node 22 with pnpm through corepack (see `CLAUDE.md`).
2. `./jobs-radar.sh --init-env` creates `.env` with a random database password and credential key.
   Back up `JOBS_RADAR_CREDENTIAL_KEY` somewhere other than the database backups.
3. `./jobs-radar.sh --quick-start` starts the database, API and worker, waits until they are
   healthy and starts the frontend. `./jobs-radar.sh --urls` prints the addresses.
4. Open the app. Add a board in **Sources**, create a profile and an intent in **Profile & intent**,
   optionally choose a local model in **AI & privacy**, then set the daily schedule in **Sources**.

## Every day

- `./jobs-radar.sh --status` and `--health` (exit 0 only if everything running is healthy).
- The sidebar footer shows the backend state, including the worker heartbeat.
- **Today** shows what is new; **Sources** shows each board's last run and why a run failed.
- Logs: `./jobs-radar.sh --logs api --lines 100` (`worker`, `db`, `frontend` too).

## After pulling a change

```bash
./jobs-radar.sh --rebuild api && ./jobs-radar.sh --rebuild worker   # when dependencies changed
./jobs-radar.sh --db-migrate                                          # when there are new migrations
```

## Stopping and cleaning

`--quick-stop` stops everything. Data lives in the Docker volume and survives restarts.
`--nuclear-reset` deletes the database volume after a typed confirmation; take a backup first.

## Checks before you trust a change

`make check` (quality gates and tests), `make check-all` (adds static analysis, secret scan, the
dependency audit and `make test-e2e`; needs network, Docker and the app running; the e2e step stops
with a message if the stack is not healthy, and CI never runs it),
`make config-check` (exposure and secrets), `make smoke` (real services, opt-in).

## Exposure

The API has no authentication in this version. `JOBS_RADAR_API_BIND` and `JOBS_RADAR_DB_BIND`
default to loopback; `make config-check` warns when either is reachable from the network. If you
expose the API, do it only on a trusted network.
