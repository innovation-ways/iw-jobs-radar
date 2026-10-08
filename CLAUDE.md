# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Jobs Radar

Local-first, single-user personal job-market intelligence system. It tracks permitted public job sources, scores jobs against an explicit Career Profile + Search Intent, and keeps a personal inbox of triage decisions. Repository: `iw-jobs-radar`. Python package: `jobs_radar`.

**Phase**: implementation; T0 (foundation), T1 (data contracts) and T2 (Greenhouse collection, Sources screen) and T3 (manual profile and intent) and T4 (extraction, matching, duplicates, inbox) and T5 (worker, schedule, digest) and T6 (AI & privacy, CV import) done; next is T7. Build order and rules are in `ai-dev/docs/14 - Implementation Guide.md` (tasks T0–T8, tick boxes there). Implement only the task the user asked for, in guide order; ask when anything is unclear. Do not assume commands or paths that are not in the docs or in this file.

## Working rules (NON-NEGOTIABLE)

- **Language**: all documentation, code, comments, docstrings, identifiers, commit messages, ADRs and design docs MUST be in English. Chat with the user may be in Portuguese or English; nothing written to the repository may be Portuguese.
- **Ask, never guess.** If a requirement, design choice or rationale is unclear, ask the user before implementing. Do not implement anything unless you are sure how and why. Raise doubts and suggestions proactively.
- If documents conflict, or a change touches data residency, privacy, scoring semantics, collection sources, external exposure or V1 scope: stop and record a proposed ADR in `ai-dev/docs/11 - Architecture Decision Log.md` instead of silently deciding.
- Do not modify the separate `cv` repository (ADR-016).

## Source of truth

Read `ai-dev/docs/` in numeric order (`00` index → `12`) before changing code. Precedence: requirements (02, 04) define *what*; HLD/LLD (05, 06) define *how*; security/privacy (08) overrides convenience. `10 - Agent Handoff Guide` has the working rules and stop conditions; `12 - V1 Operational Release Scope` defines the release boundary; `11` holds locked ADRs (001–046) and open decisions (ODR), which must not be assumed.

## Architecture (big picture)

Stack: Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic; TypeScript, React, Vite, Zod, React Hook Form; **PostgreSQL only** (no SQLite, in any environment); Docker Compose; versioned REST API under `/api/v1`. **No authentication in V1** (fixed local owner context, `owner_id` still present in the model; LAN-only) — ADR-009.

Processes: `api`, a separate `worker` (collection + scheduler; daily time and IANA time zone are GUI settings stored in the DB; manual runs are queued in the DB; a DB lock prevents duplicate runs — ADR-017), PostgreSQL, and the Vite frontend. A root-level launcher script manages them all, modelled on `../iw-doc-plan/innoforge.sh` (CLI flags for agents, `--health` exits 0 only if healthy — ADR-018). External notifications are out of V1; the in-app digest is the notification surface.

Backend layering: `api/routes` (HTTP only, no DB access) → `services` (use cases, invariants, domain exceptions) → `repositories` (data access only) → `db` models; plus `schemas` (Pydantic API boundary, never expose ORM models) and `domain`. Dependencies are injected via FastAPI `Depends`. Layout in LLD §1 (`backend/src/jobs_radar/...`). The matching module is a **pure function** with no HTTP/DB/network/LLM imports. Layer boundaries are enforced with import-linter.

Core invariants that span many files:

- **Career Profile is canonical, not the CV.** Imports create reviewable *proposals*; only accepted/edited items become facts in a new immutable `ProfileRevision`. Search Intent has its own independent revision history. Revisions, snapshots and evaluations are append-only — never update in place.
- **Uploaded CVs are never stored** (ADR-010): extracted in memory, optionally sent (redacted, after consent) to an AI provider, then discarded. Only metadata and user-reviewed source excerpts persist.
- **AI-first hybrid evaluation (ADR-021, amends ADR-004).** The LLM extracts structured job attributes and gives per-dimension judgements with quoted evidence; these are stored immutably with provider/model/prompt version. The final score is a **deterministic function of the stored judgements** (`matching-v1`: hard gates, then weighted dimensions summing to 100; no LLM in the final step). `unknown` contributes 0. A hard-constraint mismatch ⇒ `not_recommended`. Changing model/prompt creates a new evaluation, never rewrites an old one. There are no keyword-rule fallbacks: without a configured LLM, jobs are collected and shown as "not evaluated".
- Market trends (ADR-022): persist extracted attributes on a versioned taxonomy, job lifecycle (first/last seen, closed), source provenance and relevance flag from the first collection; weekly aggregates cover relevant jobs only.
- Duplicates (ADR-023): each source listing stays a `JobPosting`; listings of the same real opportunity are linked reversibly to one canonical opportunity (same company + similar title/location/description/dates); the inbox shows one item per opportunity.
- **Stance model and criteria (ADR-026):** every option of roles, work arrangements, engagement types, seniority, sectors and employer types is Preferred / Acceptable / Rejected (Rejected = hard gate). Dimensions: Role & responsibilities 25, Skills & technology 15, Work arrangement & location 15, Engagement & contract terms 10, Compensation 10, Seniority & experience 8, Domain & sector 10, Company profile 7, plus optional Benefits & flexibility and Qualifications at 0. A weight of 0 means the dimension is excluded (shown greyed in the UI). Details: `ai-dev/docs/13 - Domain Schemas and Matching Rules.md`.
- Every `MatchEvaluation` persists profile revision ID, intent revision ID, job source hash, policy version and per-dimension evidence.
- **Job facts vs. personal state are separate**: `JobPosting`/`JobSnapshot` (shared, source-authoritative) vs. `JobInboxItem`/`InboxEvent` (per-owner, unique `(owner_id, job_opportunity_id)`: the inbox is keyed by opportunity, ADR-028). Inbox transitions follow the table in LLD §3; every transition emits an `InboxEvent`; `is_shortlisted` is an independent boolean. Material source changes (LLD §5) move eligible items to `updated_unread`; cosmetic changes do not.
- **Adapters isolate the outside world**: `ExtractionProvider`, `LLMProvider`, `JobSourceAdapter` (Protocols). Adapters never receive repository sessions and never write profile revisions, scores or inbox rows. Provider output is schema-validated before persistence. A source or provider failure must never block other sources, manual workflows or historical browsing.
- **Sources are configured in the database** (ADR-012): URL, rate limit, enabled flag and optional encrypted write-only credential, managed from the frontend. The frontend shows per-source status: last run time, outcome, number of postings, and error reason. The first source type is the Greenhouse Job Board API (ADR-015, research `docs/research/R-00169-job-source-api-evaluation.md`); a source is one company board, so the board-token list is GUI-managed and validated on add. Lever and Ashby come later through the same adapter interface.
- V1 limits: pay is compared in the same currency only (currency conversion is a pending improvement); employee pay is entered as linked monthly/annual fields with a 12/14 payments choice (annual canonical), contractors by day rate only; locations are resolved offline with `geonamescache` (GeoNames data, CC BY 4.0: credit GeoNames in the UI).
- Collection pipeline: scheduler → source adapter → normalise → fingerprint/dedupe → snapshot → material-change detection → evaluate enabled intents → inbox/digest. Fixture and live data use the same pipeline.
- API conventions: IDs are integers (BIGSERIAL), UTC ISO-8601 timestamps, optimistic concurrency (`expected_version` / `expected_current_revision`), errors as `{error:{code,message,details,request_id}}` with `422` invalid input, `404` unknown, `409` version/state conflict, `503` external dependency unavailable.

## Frontend design

Direction from research R-00170 (`docs/research/R-00170-frontend-design-research.md`): calm, neutral, colour-only-for-meaning; at most two disclosure levels (inbox row → detail panel); keyboard-first list+detail inbox; density toggle; Inter ~14px with tabular numerals; every status/fit shown with text or icon, never colour alone (WCAG 1.4.1); fit score rendered as an accessible `meter`; sparklines for trends; shadcn/ui + Radix + Tailwind. The agreed visual reference is the static mock-up `docs/design/frontend-mock.html` (synthetic data; accent option still to be chosen).

## Commands

Run from the repository root (`make help` lists everything). Prerequisites: Docker, `uv`, Node 22 with pnpm through corepack (`corepack enable --install-directory ~/.local/bin pnpm`; the version is pinned in `frontend/package.json`; pnpm 12 did not work through corepack here).

```bash
make                              # = make help: every command, grouped and coloured (the list is test-enforced to be complete)

./jobs-radar.sh                   # interactive menu: start/stop, health, frontend, database, logs, tests, addresses
./jobs-radar.sh --init-env        # create .env (random DB password and credential key); never commit it
./jobs-radar.sh --quick-start     # db + api + worker (Docker), wait healthy, start frontend (Vite, outside Docker)
./jobs-radar.sh --status | --health | --urls | --psql | --db-migrate
./jobs-radar.sh --logs api --lines 50 | --restart worker | --rebuild api | --quick-stop | --help
./jobs-radar.sh --tests [unit|integration|backend|frontend|e2e|quality|all]   # wrappers around make
# Colours only appear on a terminal (FORCE_COLOR=1 forces, NO_COLOR=1 disables). --health exits 0 only if healthy.
# JOBS_RADAR_ENV_FILE points the launcher at another env file (used by its tests).

make up / down / restart / status / health / urls / logs SVC=api   # the same launcher actions from make
make quality                      # backend gates: ruff, format check, mypy strict, import-linter, bandit, licences, column docs
make quality-frontend             # eslint (0 warnings), prettier, tsc, licence check
make test                         # backend unit + integration (needs Docker; PostgreSQL testcontainer)
make test-unit                    # backend unit only, no Docker
make test-file FILE=tests/unit/test_settings.py | make test-k K=inbox | make test-failed
make test-frontend / test-frontend-watch / fe-coverage   # Vitest
make test-e2e                     # Playwright against the running stack (see below)
make coverage / coverage-html     # backend coverage, fails under 80%; HTML report in backend/htmlcov
make security-sast                # semgrep (needs network for rule packs)
make secret-scan                  # gitleaks over git history + staged changes (the local .env is not scanned)
make openapi / make api-client    # export backend/openapi.json, regenerate the typed frontend client
make seed-dev-sources             # add the 14 research boards as DISABLED sources to the dev DB (no network; dev env only)
make docs-schema                  # regenerate docs/database/schema.md (data dictionary; a test fails if stale)
make check                        # quality + quality-frontend + test + test-frontend
make check-all                    # check + security-sast + secret-scan
make clean                        # delete caches and generated reports
```

When you add a make target, give it a `## description` and list it in `.PHONY` (and in a `##@` section): a unit test fails otherwise.

Single tests: `cd backend && uv run pytest tests/unit/test_settings.py::test_defaults_match_adr_019_and_adr_032 -q`; `cd frontend && pnpm test src/theme/ThemeProvider.test.tsx`.

- Changing the API: run `make api-client` and commit `backend/openapi.json` and `frontend/src/api/schema.d.ts` (a unit test fails if the snapshot is stale).
- Playwright never downloads browsers. `frontend/playwright.config.ts` uses `JOBS_RADAR_CHROMIUM_PATH` or the executable in `.playwright/cli.config.json` (local, git-ignored; currently `chromium-1228`). Agents use `playwright-cli` for ad-hoc browsing; it blocks `file:` URLs, so serve static files over HTTP.
- Pick up `.env` ports automatically: the launcher, Compose and Vite all read `JOBS_RADAR_*`.
- The test suites block network sockets except loopback and the Docker socket; never remove that.

## Technical decisions (ADR-029 to ADR-046)

- Layout: `backend/` (`src/jobs_radar/{api,schemas,services,repositories,db,domain,adapters,worker,core}`), `frontend/`, root `Makefile`, `docker-compose.yml` (+ `docker-compose.dev.yml`), `.env.example`, launcher `jobs-radar.sh`. Import-linter: adapters never import repositories/db; `domain` and the matching engine import nothing outward.
- PostgreSQL 18; SQLAlchemy 2 async + psycopg 3; Alembic; primary keys are `BIGINT GENERATED BY DEFAULT AS IDENTITY` named `{table}_id`; JSONB payloads validated by Pydantic with `schema_version`; DB triggers make revision/snapshot/extraction/evaluation/event tables append-only.
- Worker is a separate process polling the DB (no Celery/Redis): schedule and queued runs in tables, `FOR UPDATE SKIP LOCKED`, advisory lock, heartbeat used by `/readyz`.
- Config via `pydantic-settings`, prefix `JOBS_RADAR_`; defaults: API 8100, frontend 5180, DB 5440 (all in `.env`); API binds `127.0.0.1` unless `JOBS_RADAR_API_BIND` says otherwise (no authentication in V1). Credentials: Fernet, key from env.
- One httpx client factory + `UrlGuard` (SSRF) for every outbound call; tests use `respx` and `pytest-socket`. Ollama (local) is reached from containers via `host.docker.internal`, allowed only with `JOBS_RADAR_ALLOW_LOCAL_PROVIDERS`.
- Collection (ADR-042, ADR-045): the worker executes queued runs (the API only queues them); a posting closes only after two consecutive successful runs without it; collected jobs keep every attribute `unknown` until AI extraction. Sources are added by validated board token in the Sources screen; the dev seed is never test data.
- Profile and intent (ADR-043): a save with no change creates no revision (`created: false`), a stale `expected_current_revision` is 409, restore appends a new revision; skills are typed by name and resolved to canonical skills; unchanged items keep provenance. Places are resolved offline with `geonamescache` (credit GeoNames in the UI); the weights impact preview endpoint arrives in T4. Frontend drafts are plain React state with targeted validation (RHF/Zod for flat forms).
- Extraction, matching, duplicates and inbox (ADR-044): AI extraction is opt-in (`JOBS_RADAR_EXTRACTION_ENABLED`, default off) with local Ollama (`qwen3:8b`, `qwen3-embedding:8b`, 12,000 characters); the model's answer is salvaged field by field and every quote is checked verbatim; `matching-v1` is a pure module in `domain/matching/` (no AI in the final score); evaluations are append-only and new weights apply to new jobs (rescore on request, no model call); only same-company listings from different sources are linked (`dedup-v1`); the inbox is keyed by opportunity and every open one is listed, scored or "not evaluated".
- AI & privacy (ADR-046): the database decides (No AI by default; env only seeds the first local connection); CV import may use a remote OpenAI-compatible provider only after per-CV consent and with contact details redacted, job analysis is local only; credentials are Fernet-encrypted and write-only; uploads are processed in memory and the text is held ≤30 min in a process-local store; proposals are reviewed item by item into a new revision.
- Dependencies: no AGPL or proprietary runtime dependency (e.g. no PyMuPDF; use `pypdf`, `python-docx`, `nh3`, `rapidfuzz`, `geonamescache`). Frontend: Vite, React, TS strict, React Router, TanStack Query, RHF + Zod, Tailwind v4, shadcn/ui, self-hosted Inter, generated OpenAPI client, SVG sparklines.

## Security and privacy rules

- Default is **No AI**. Credentials (AI provider and source) are encrypted at rest, write-only in API/UI, and never logged, exported or returned. The encryption key comes from an environment variable defined in an untracked `.env` file (ADR-013); only `.env.example` (variable names, no values) is committed.
- Remote LLM calls: extracted text only, after redaction and per-document consent; never send the raw original document; never silently fall back from local to cloud.
- Custom provider/source URLs must be SSRF-validated (HTTPS default, block link-local/metadata, bounded timeouts, no redirects into blocked targets).
- Validate upload MIME/extension/size server-side; never write uploads to disk.
- Fixtures are synthetic only: no real CVs, personal data, credentials or live job payloads in the repo, screenshots or CI artefacts.
- Out of scope: auto-apply/form filling, authenticated job-board scraping as a core source, public exposure, SaaS billing, generic chat/agents, claiming a fit score predicts hiring.
- Do not start/stop/reconfigure production services or expose the app without explicit approval.

## Code documentation standards (NON-NEGOTIABLE)

Code without meaningful documentation is incomplete. All in English.

- **Python**: every `.py` file starts with a module docstring; every class has a docstring; every public function/method has a docstring (one-line summary, plus args/returns/raises when non-trivial). Inline comments are required for non-obvious logic, security-sensitive code, lazy imports, intentionally broad exception catches, and performance-critical decisions. Not required for trivial getters/`__repr__`.
- **TypeScript/React**: JSDoc on exported functions and components (purpose and props); inline comments explain the "why".

## Development process

- **TDD is mandatory** (no exceptions): RED (failing test) → GREEN (minimal code) → REFACTOR. Focused commits.
- Workflow per task: design review → implementation with per-agent code review (max 5 fix cycles, `.iw-orch.json`) → global review → quality validation → commit. Pipeline in `ai-dev/workflow.md`; design docs in `ai-dev/design/active/` from `ai-dev/templates/` via the `iw-new-feature` / `iw-new-incident` / `iw-new-cr` skills; specialist agents in `.claude/agents/`. Work item IDs come from `iw next-id --type <feature|incident|cr>`, not from files.

### Quality gates (all must pass before any commit)

| Gate | Tool | Threshold |
|------|------|-----------|
| Lint / format | `ruff check`, `ruff format --check` | 0 errors / 0 diffs |
| Types | `mypy` | 0 errors |
| Architecture | `import-linter` (`make arch-check`) | 0 contract violations |
| Security | `bandit` (0 HIGH/CRITICAL), `semgrep` (`make security-sast`, 0 findings) | |
| Unit + property tests | `pytest tests/unit/` (hypothesis for properties) | 100% pass |
| Integration tests | `pytest tests/integration/` | 100% pass |
| Coverage | `pytest --cov` | ≥ 80% overall |
| E2E (API) | `make test-e2e-api` | 100% pass |
| Frontend | Vitest, Playwright smoke | 100% pass |
| DB column docs | `make docs-check` | 0 undocumented columns |

Secondary (periodic, non-blocking): vulture (`make dead-code`), deptry (`make dep-check`), schemathesis (`make contract-test`). These `make` targets are the intended interface; none exist until the repo is scaffolded — confirm exact commands with the user then.

### Testing rules

- Ordinary tests need no cloud credential, real CV or live source; use synthetic fixtures and adapter test doubles. Live provider/source smoke tests are explicit opt-in commands, never default CI.
- **Tests must never make real network requests or use the development source seed** (the Greenhouse board-token seed is for local development only). Stub the HTTP layer with recorded synthetic responses and block outbound network in the test session so an accidental real call fails the test (ADR-015).
- **Integration tests MUST NEVER connect to the development database.** Each session uses a temporary PostgreSQL container via `testcontainers[postgres]`, with Alembic migrations applied on it. Never hardcode DB URLs/credentials or add fallbacks pointing at a dev DB. DB, `app`, `client`, `db_session` fixtures live in `tests/integration/conftest.py`, not the root `tests/conftest.py`.
- `app`/`client` fixtures are session-scoped (single event loop: `asyncio_default_fixture_loop_scope = "session"`); tests must not assign to `app.state` directly — use `monkeypatch.setattr(app.state, ...)`.
- Headless WSL/Linux: use **`playwright-cli`** for all browser interaction (run `playwright-cli kill-all` first). Never use `agent-browser`, `npx playwright install`, or `chromium.launch()` scripts.

### Database conventions

- **Primary keys are BIGSERIAL named `{table_name}_id` — NEVER a bare `id`** (e.g. table `job_posting` → `job_posting_id`). Foreign keys are BIGINT and reuse the referenced primary key's exact name (e.g. `job_inbox_item.job_posting_id`). The same rule applies to API path parameters, query parameters and JSON fields, and to Python attribute names.
- Role-named foreign keys are the only allowed exception to that rule (self-references and double references): `current_profile_revision_id`, `primary_job_posting_id`, `from_/to_job_snapshot_id`, `skill_id_a/b`, `replaced_by_taxonomy_term_id`, `introduced_in_taxonomy_version_id` (ADR-041).
- snake_case tables/columns; timestamps TIMESTAMPTZ in UTC. Enumerations are text + a named CHECK constraint (use `enum_check`); constraint names must fit PostgreSQL's 63 characters.
- Build columns with the helpers in `db/columns.py` (`pk_column`, `fk_column`, `text_column`, ...): they guarantee a `comment`.
- Immutable tables are protected by triggers; the only bypass is `repositories/deletion.py` (audited). `job_extraction` is mutable only while `pending`.
- Migrations import `db/triggers.py` and `domain/taxonomy_seed.py`: never edit those constants, add a new migration. Autogenerate against the dev DB with `cd backend && uv run alembic revision --autogenerate -m ...`, then review: circular FKs and triggers need manual edits.
- Tests use the factories in `backend/tests/factories.py` and sample data in `backend/tests/data.py` (synthetic only); DB tests flush but never commit.
- Audit columns: `created_at` (and `updated_at` on mutable tables) only. No soft deletes (`deleted_at`) and no `created_by` — deletion is real (UC-08) and revision/snapshot/evaluation/event tables are append-only.
- Every `mapped_column()` MUST have a `comment=` (one sentence); every model class MUST have a docstring. Enforced by `make docs-check`.
- Alembic migration for every schema change, reversible where practical.

### Commits and branches

- Conventional Commits: `<type>(<scope>): <description>`; types `feat|fix|docs|refactor|test|chore`; scopes `api|db|worker|frontend|ci|config`. Reference the work item.
- For now all work is done directly on `main` (no `manual-dev` branch or worktrees yet). Keep `main` stable: every commit passes the quality gates. Branch/worktree workflow may be introduced later; ask before creating branches or worktrees.
