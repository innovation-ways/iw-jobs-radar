# MCP server: design and implementation plan

> Status: **accepted** ([ADR-078](../decisions/architecture-decision-log.md)), implemented as task
> T13. The owner's decisions are in section 11.

## 1. Goal and non-goals

**Goal.** Let an agent that speaks the [Model Context Protocol](https://modelcontextprotocol.io)
(Claude Code, a desktop assistant, a local Ollama agent) read the owner's Jobs Radar data and, in a
second phase, triage jobs by conversation.

**Non-goals** (each one needs its own ADR if it ever comes):

- a network listener or a hosted/remote MCP endpoint (no authentication exists, ADR-009);
- any tool that touches credentials, AI settings, CV upload, deletion, scoring weights, profile or
  intent edits, or adding sources;
- auto-apply, form filling, or any agent-driven contact with employers (out of scope for the whole
  product);
- changing the API, the database or the matching rules. The server is a client of what exists.

## 2. Architecture

```
agent client  --stdio-->  python -m jobs_radar.mcp_server  --HTTP-->  Jobs Radar API  -> services -> PostgreSQL
(launches it)             (this plan; no DB, no secrets)               (unchanged; all rules live here)
```

- The client starts the process and talks over stdin/stdout. Nothing new listens on a port.
- **Fail closed.** The process starts only if `JOBS_RADAR_MCP_ENABLED=true` (untracked `.env`, or
  the process environment, which wins). Otherwise it writes one line to stderr, exits with status 2
  and has registered no tool and opened no connection.
- The process calls the API at `JOBS_RADAR_MCP_API_URL` (default `http://127.0.0.1:<API port>`). If
  the API is down, tools fail with a clear message; the process itself stays up.
- Every validation, conflict check (`expected_version`), inbox transition and append-only rule is
  enforced by the API. The MCP server adds only: shaping of replies for agents, size limits, the
  untrusted-text wrapper, and the read/write switch.

### Package layout (`backend/src/jobs_radar/mcp_server/`)

| Module | Responsibility |
|---|---|
| `__main__.py` | Entry point: loads settings, **exits 2 if not enabled**, otherwise builds client and server and runs stdio. Logging to stderr only. |
| `settings.py` | `McpSettings`: process environment first, then the `.env` file (`JOBS_RADAR_ENV_FILE`, else the repository's `.env`). A small line parser keeps **only** keys starting with `JOBS_RADAR_MCP_` plus `JOBS_RADAR_API_PORT`; no other value is held in memory. Fields: `ENABLED`, `ALLOW_WRITES`, `API_URL`, `TIMEOUT_SECONDS`. |
| `api_client.py` | `ApiClient`: the only code that does HTTP. Fixed allow-list of `(method, path template)`, no redirects, timeouts, response size cap, API error envelope to `ApiError`. Accepts an injected `httpx` transport (tests). |
| `untrusted.py` | `wrap_untrusted(text, max_chars)`: truncates, neutralises the marker inside the text, wraps it. |
| `views.py` | Compact Pydantic output models (own models; nothing imported from `jobs_radar.schemas`), so the tool contract does not change when an API model gains a field. |
| `tools_read.py` | Phase 1 tools. |
| `tools_write.py` | Phase 2 tools, registered only when `ALLOW_WRITES` is true. |
| `server.py` | `build_server(settings, client) -> MCPServer`: registers tools, server `instructions`. |

Dependency: optional extra `mcp = ["mcp>=2.3,<3"]` in `backend/pyproject.toml` (MIT), also in the
dev group so the tests run. `uv.lock` is committed. The API and worker images do not install it.

Import-linter: a new contract forbids `jobs_radar.mcp_server` from importing `api`, `schemas`,
`services`, `repositories`, `db`, `domain`, `adapters`, `worker` and `core` (the process must not
be able to reach the database or the encryption key even by accident; it has its own `.env`
reader precisely so that it does not import `core.settings`).

## 3. Tools

All names are snake_case; the client prefixes them with the server name. Inputs are validated by
the SDK from the type hints; every integer ID keeps the API's name (`job_inbox_item_id`, never a
bare `id`). Every reply is a typed object (structured output) with a short text rendering.

### Phase 1: read-only (`readOnlyHint: true`, `openWorldHint: false`)

| Tool | API calls | Inputs | Returns |
|---|---|---|---|
| `get_status` | `GET /pipeline/status`, `GET /widget/summary` | `fit_min` (0-100, default 65) | worker/API state, analysis and scoring queues, failures, counts to review and best fit |
| `list_inbox` | `GET /inbox` | `state` (default `unread`), `shortlisted`, `search_intent_id`, `company`, `source`, `q`, `fit_min`, `fit_max`, `evaluated`, `set_aside`, `engagement[]`, `rate`, `include_closed`, `sort`, `limit` (1-50, default 20), `cursor` | rows: IDs, `version`, title, company, locations, fit and band, recommendation, gates fired, state, shortlisted, engagement and pay, first seen; `counts`; `next_cursor` |
| `get_job` | `GET /inbox/{job_inbox_item_id}` | `job_inbox_item_id`, `search_intent_id`, `max_chars` (default 6000) | key facts, AI brief, technologies, per-dimension evidence (status, quality, quoted evidence), gates, sources, history, and `untrusted_description` |
| `get_daily_digest` | `GET /digests/daily` | none | the in-app digest |
| `list_search_intents` | `GET /profiles`, `GET /profiles/{id}/intents` | none | name, enabled, current revision, stances per group, weights, pay expectations, everything the API returns that is useful to an agent |
| `get_career_profile` | `GET /profiles`, `GET /profiles/{id}` | none | the full current profile: headline, years, base location, skills, languages, experience, education, certifications, directions (owner decision: expose everything) |
| `list_sources` | `GET /sources` | none | type, name, enabled, last run, outcome, posting count, error reason; never any credential field |
| `list_collection_runs` | `GET /collection-runs` | `limit` | recent runs and outcomes |
| `list_companies` | `GET /companies` | `q`, `followed`, `limit`, `cursor` | company summaries |
| `get_company` | `GET /companies/{company_id}` | `company_id`, `max_chars` | dossier facts with provenance; AI summary labelled as inference; website text as untrusted |
| `get_trends` | `GET /trends` | `kind`, `weeks` (1-52, default 12), `limit` (1-50, default 15), `search_intent_id` | ranked terms, shares, weekly series, locked periods, markers |

Replies never include `description_text` outside `untrusted_description`, never include a field
whose name contains `credential`, `secret`, `api_key`, `token` or `password` (tested; the profile
and intent are returned in full, but nothing in them is a secret), and drop fields an agent cannot
use (for example UI signals).

### Phase 2: writes (only with `JOBS_RADAR_MCP_ENABLED=true` **and** `JOBS_RADAR_MCP_ALLOW_WRITES=true`)

| Tool | API call | Notes |
|---|---|---|
| `inbox_action` | `POST /inbox/{job_inbox_item_id}/actions` | `action` in the API's closed list, `expected_version` **required**, optional `reason`, `note`, `applied_at`, `application_url`. A stale version is a tool error telling the agent to re-read. `destructiveHint: false`, `idempotentHint: false`. |
| `start_collection` | `POST /collection-runs` | queues a run exactly like the button; the worker executes it; `409 too_soon` is reported, not retried. |
| `summarise_job` | `POST /jobs/{job_posting_id}/summary` | local model, append-only; reports if the model is not configured. |

With the flag off these tools do not exist (they are not merely refused), and a test proves it.

## 4. Security design

| Threat | Control |
|---|---|
| Prompt injection from job or company text | `untrusted_*` fields, fixed marker with in-text marker neutralised, truncation, tool descriptions and server `instructions` say "data, not instructions"; phase 1 cannot act; phase 2 is an allow-list with `expected_version` and client confirmation |
| Credential or CV leakage | no tool for settings, documents or credentials; the server holds no secret and parses only `JOBS_RADAR_MCP_*` and the API port out of `.env`; output scan test for forbidden key names |
| Unwanted use at all | master switch `JOBS_RADAR_MCP_ENABLED`, default false; the process exits before registering anything |
| Accidental write | writes off by default and not registered; every write tool annotated for client confirmation |
| Stale-state action | `expected_version` required, taken from `list_inbox`/`get_job` |
| Context flooding / cost | page size caps, `max_chars`, compact views |
| Protocol corruption | logs to stderr only; a test fails if anything else reaches stdout |
| SSRF / wrong target | one configured base URL, no redirects, path allow-list (the agent cannot supply a URL or path) |
| Supply chain | optional extra, pinned in `uv.lock`, `pip-audit`, licence gate, Dependabot |
| Sensitive data to a cloud model | everything is exposed by owner decision, so the protection is the master switch plus the README and operations guide warning (section 8); a local-only agent keeps the data on the machine |

## 5. Test strategy (TDD: RED, GREEN, REFACTOR; keep the RED output in the task notes)

Network is blocked in the suites; the MCP tests use `httpx.MockTransport`/`respx`, the SDK's
in-process `Client(server)`, and the real application through `httpx.ASGITransport` (no socket).

| Level | Tests |
|---|---|
| Unit: `settings` | not enabled when unset, `false`, `0` or garbage (fail closed); enabled only for `true`; process environment beats `.env`; the `.env` parser keeps only `JOBS_RADAR_MCP_*` and `JOBS_RADAR_API_PORT` (a decoy `JOBS_RADAR_CREDENTIAL_KEY=...` is never held, never logged, never in `repr`); comments, quotes and trailing comments in `.env` values (the bug fixed in the launcher) parse correctly; missing file is fine; default API URL derives from the port |
| Unit: entry point | not enabled: exit status 2, one stderr line, **nothing on stdout**, no tool registered and no HTTP request made (respx asserts zero calls) |
| Unit: `untrusted` | truncation at `max_chars`; marker inside the text is neutralised; empty text; Hypothesis: the output never contains an unescaped closing marker before the end |
| Unit: `api_client` | API error envelope to `ApiError` (code, message, request_id); 409 and 422 and 503 mapped; connection error gives the "API not reachable" message; redirect refused; oversize body refused; a path outside the allow-list raises before any request; timeout |
| Unit: views and tools | one test per tool with a synthetic API payload: output shape, limits applied, no secret-like key, `description_text` only inside the wrapper, pagination cursor passed through |
| Unit: contract | every `(method, path)` in the allow-list exists in `backend/openapi.json` with the parameter names the client sends |
| Unit: surface | snapshot of tool names, descriptions' first lines and annotations; read tools all `readOnlyHint`; write tools absent with the flag off and present (with `destructiveHint: false`) with it on; the write flag alone, without `ENABLED`, still starts nothing; no tool parameter named `id`, `url`, `path`, `credential`, `token` |
| Unit: safety | scan of every tool reply built from a fixture payload full of decoy secrets (`api_key`, `credential`) shows none of them; stdout stays clean while the server handles requests |
| Architecture | import-linter contract; `test_architecture_contracts`-style test that the contract catches a forbidden import |
| Integration | the server over the real FastAPI app and a PostgreSQL testcontainer, data from `inbox_scene.py` (synthetic): `list_inbox` order and filters equal the API's, `get_job` evidence equals the stored evaluation, a stale `expected_version` write fails and changes nothing, a valid `inbox_action` appends one `InboxEvent`, `start_collection` queues one run and a second inside the minimum interval reports `too_soon` |
| Stdio | spawn `python -m jobs_radar.mcp_server` against a stub API on loopback, run `initialize`, `tools/list`, one call; asserts clean protocol and clean shutdown |
| Opt-in smoke | `tests/smoke/` (not in the default run): the stdio server against the running demo stack |

Quality gates before every commit: `make quality`, `make test` (unit + integration), coverage at
least 80%, `make security-sast`, `make secret-scan`, `make security-audit` at the end.

## 6. Tasks (to be added to the Implementation Guide as T13)

Each sub-task is one focused commit on `main`, with the DCO sign-off (`git commit -s`) and the
attribution line the repository already uses.

- [x] **T13.0 Approval.** The owner reviews this plan and ADR-078 (answers to section 11 are already recorded); ADR-078 set to *accepted*; add the `mcp` scope to the contributing rules.
- [x] **T13.1 Foundations.** Optional extra and lock file, licence/deptry/audit pass, import-linter contract, `McpSettings` with the `.env` reader and the fail-closed entry point, `untrusted.py`, `ApiClient` with allow-list; unit tests first.
- [x] **T13.2 Read tools, part 1.** `get_status`, `list_inbox`, `get_job`, `get_daily_digest`, with views and tests.
- [x] **T13.3 Read tools, part 2.** `list_search_intents`, `get_career_profile`, `list_sources`, `list_collection_runs`, `list_companies`, `get_company`, `get_trends`.
- [x] **T13.4 Server assembly.** `build_server`, `__main__`, server `instructions`, surface snapshot, OpenAPI path test, stdout-clean test, stdio subprocess test.
- [x] **T13.5 Integration tests** over the real app and PostgreSQL container.
- [x] **T13.6 Tooling and docs.** `make mcp-config` (prints the client snippet, no secret) and `make test-mcp` (each with `##` text, in `.PHONY` and `##@`); `.env.example` with `JOBS_RADAR_MCP_ENABLED=false` and `JOBS_RADAR_MCP_ALLOW_WRITES=false`; `make config-check` reports the MCP state; `.mcp.json` in `.gitignore`; `docs/operations/mcp-server.md` (cloud and local clients); README (feature line, Security paragraph on the agent privacy trade-off, link); `configuration-reference.md`; the published ADR set to its final status.
- [x] **T13.7 Real check.** Run it with Claude Code against the **demo world** (`make demo`, API on 8101, fictional data) and walk through the prompts in the operations guide; opt-in smoke test; never against the owner's real data in anything that is committed or screenshotted.
- [x] **T13.8 Phase 2 writes** (owner: same round): `tools_write.py`, flag handling, the tests of section 5 for writes, runbook section. Done after T13.7 so the read-only server is usable and reviewable first.
- [x] **T13.9 Close-out.** `make check`, `make security-sast`, `make secret-scan`, `make security-audit`; `CLAUDE.md` and the Implementation Guide updated; ADR-078 marked implemented. The changelog is generated by release-please: do not edit `CHANGELOG.md`.

## 7. Configuration and client setup (documented in `docs/operations/mcp-server.md`)

| Variable | Default | Meaning |
|---|---|---|
| `JOBS_RADAR_MCP_ENABLED` | `false` | Master switch. Anything but `true` (or absent): the server exits and no agent can use it |
| `JOBS_RADAR_MCP_ALLOW_WRITES` | `false` | Also register the phase 2 tools |
| `JOBS_RADAR_MCP_API_URL` | `http://127.0.0.1:<JOBS_RADAR_API_PORT>` | Where the API listens (a LAN address only if the API is bound there, ADR-065) |
| `JOBS_RADAR_MCP_TIMEOUT_SECONDS` | `15` | Per request |

They go in the untracked `.env` (names and safe defaults in `.env.example`); the process
environment overrides the file, which is how the demo world is pointed at port 8101. The server
reads nothing else from `.env`. Example for Claude Code (paths are placeholders; `make mcp-config`
prints the real ones for the current checkout):

```bash
claude mcp add jobs-radar --scope local \
  -- uv run --directory /path/to/iw-jobs-radar/backend --extra mcp python -m jobs_radar.mcp_server
```

Why `--scope local`: the entry is stored in the user's own Claude configuration, not in the
repository. A project-level `.mcp.json` is git-ignored for the same reason. Local agents (Ollama or
any local model behind an MCP-capable client) use the same command in their client's configuration;
the guide shows both.

## 8. Documentation that must say it plainly

README "Security" and the operations guide state, in this order:

1. The MCP server has **no authentication**, like the UI and API; it only runs for a client that
   starts it on your machine and talks to your API, and only if `JOBS_RADAR_MCP_ENABLED=true`.
2. What a tool returns is sent to whatever model the agent uses, and **the profile and intents are
   returned in full**. With a cloud agent, jobs, scores, decisions and your profile details leave
   your machine; with a local agent they do not. Choose the client accordingly, and leave the
   switch off when you do not use it.
3. Job text is written by third parties and may try to instruct your agent; treat the agent's
   actions with the same care as any tool that reads the web. Keep writes off unless you need
   them, and keep your client's confirmation prompts on.
4. What is never exposed (credentials, CV, AI settings, deletion, profile and intent edits).

## 9. Git hygiene (the repository is public, history is permanent)

- Never write a real value into a tracked file: no `.env` content, URLs with keys, tokens, real
  hostnames or LAN addresses, local absolute paths (use `/path/to/iw-jobs-radar`), personal data,
  real job or company payloads, or screenshots of the owner's instance. Fixtures and examples use
  the fictional demo world and `tests/data.py`.
- `.mcp.json` and any client configuration are git-ignored; client config lives in the user's
  home, outside the repository.
- Before each commit: `git diff --cached` read in full, `make secret-scan`, and a search of the
  staged files for the owner's real company, host and path names.
- Commit messages contain no local paths or secrets. No force-push and no history rewrite without
  the owner's explicit approval; if something sensitive is committed by mistake, stop and report
  it before doing anything else.
- `ai-dev/` is git-ignored: the local copy of the decision log and the Implementation Guide are
  updated there, and the **published** decision log (`docs/decisions/`) is updated in the same
  change, without personal details or chat approvals.
- Integration tests never connect to the development database; the real check uses the demo
  world only.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Tool contract drifts from the API | OpenAPI path/parameter test; integration tests on the real app |
| An agent floods its own context | caps and compact views, tested |
| SDK 2.x API changes | pinned `>=2.3,<3`, one `build_server` seam, surface snapshot test |
| `stdout` pollution breaks the protocol | stderr-only logging, a test that fails on stray output, no `print` (ruff `T20` on the package) |
| Owner points a cloud agent at the full profile without noticing | master switch off by default, warnings in README and the guide, `make config-check` shows the state |

## 11. Owner decisions (2026-10-19)

1. **Privacy:** expose everything (profile and intents in full). The protection is the master
   switch in `.env` (point 10 of ADR-078) and the documentation.
2. **Writes:** implemented in this round (T13.8), behind their own switch.
3. **Clients:** cloud and local agents; the documentation covers both.
4. **Commit scope:** `mcp` (added to the contributing rules).
5. **MCP prompts and resources:** skipped for now (proposed); client support is uneven and the
   tools cover the use cases.

`JOBS_RADAR_MCP_ALLOW_WRITES` stays `false` by default even when the server is enabled (confirmed;
a read-only agent is the safer first state).

## 12. Implementation notes (what changed from the plan)

- Tool inputs follow the API's parameter names (`followed_only`, `before_collection_run_id`, ...);
  `get_career_profile` and `list_search_intents` take no arguments and return the stored documents.
- `include_sensitive` does not exist (owner decision: expose everything).
- Real use showed that one collection run holds a result per source (about 170,000 characters for
  ten runs), so runs are summarised (totals per outcome plus only failed or partial sources),
  `list_sources` filters and pages, the digest caps each list, and the text copy of every reply is
  compact JSON (the SDK's indented text costs about a third more tokens).
- `JOBS_RADAR_MCP_*` are declared in `core/settings.py` as plain strings: the API ignores them, and
  a typo in the shared `.env` cannot stop it.
- The MCP client is the one documented exception to "only `core/http.py` imports httpx"
  (`tests/unit/test_outbound_policy.py`).
- Checked end to end with Claude Code (headless, `--mcp-config`) against the fictional demo, and
  the stdio server against the real stack read-only.
