
# Jobs Radar — Architecture Decision Log

> **About this published copy.** This is the maintainer's decision log, published with the code.
> "Document 13" and "doc 13" are published as
> [`docs/design/domain-schemas-and-matching-rules.md`](../design/domain-schemas-and-matching-rules.md).
> The other numbered documents (for example "document 07") belong to the maintainer's design pack,
> which is not part of this repository; the decisions here are meant to be readable on their own. The owner is the maintainer. Personal details and the owner's chat
> approvals were removed or translated when the log was published; the decisions are unchanged
> except for ODR-007 and ADR-048 item 6, which were updated to the licence now in use.

## Purpose

This is the compact decision record for implementation agents. It prevents re-opening deliberate product choices or silently making architectural commitments that need owner approval.

## Accepted decisions

### ADR-001 — Local-first operational V1

**Decision:** Build a local/LAN application with real permitted source collection, scheduler, and optional local/cloud AI from V1; do not expose it publicly.

**Why:** The product is only useful when it monitors the real market, while local-first deployment preserves privacy and control.

**Consequence:** V1 includes a private operational deployment, scheduler, and source/provider integrations. Public reverse proxy/SaaS exposure is not part of V1.

### ADR-002 — Career Profile is canonical; CV is evidence/input

**Decision:** CV/document imports create reviewable proposals; accepted/editable Career Profile revisions are canonical.

**Why:** A CV is incomplete and target-specific. An editable profile supports reuse, provenance, and OSS users.

**Consequence:** No provider or parser may write canonical facts directly.

### ADR-003 — Intent is separate and versioned

**Decision:** Search Intent has an independent revision history from the Career Profile.

**Why:** Job-search goals change faster than career history.

**Consequence:** Every evaluation stores both revision IDs.

### ADR-004 — Deterministic scoring is authoritative

**Decision:** Fit score uses documented hard gates and deterministic weighted dimensions. LLMs may enrich text only.

**Why:** Users need to understand/reproduce why a job is recommended; a model score is neither stable nor objectively predictive.

**Consequence:** AI provider changes must not alter the score for unchanged normalised data/profile/intent.

### ADR-005 — Unknown is not favourable

**Decision:** Missing evidence yields `unknown` and zero positive contribution.

**Why:** This avoids accidentally rewarding opaque roles.

**Consequence:** The UI must show missing information rather than hiding it behind a high score.

### ADR-006 — Inbox state is personal data, separate from jobs

**Decision:** Read/shortlist/ignore/archive/applied state is held in `JobInboxItem`, not `JobPosting`.

**Why:** The same job can have different lifecycle decisions per user/profile, and source facts must remain clean.

**Consequence:** A unique owner/job record plus immutable Inbox Events is required.

### ADR-007 — AI is optional and provider-neutral

**Decision:** Support no-AI, local, and compatible/cloud providers through adapters; secrets are write-only.

**Why:** Privacy, cost, availability, and future OSS portability require no vendor lock-in.

**Consequence:** Fixture provider is mandatory for tests; No-AI, local, and cloud-compatible provider adapters are release requirements.

### ADR-008 — Direct public sources are the V1 priority

**Decision:** V1 collection prioritises public ATS/career endpoints, feeds, and curated companies; authenticated-board scraping is not a core dependency.

**Why:** Better source provenance, reliability, and terms-of-service posture.

**Consequence:** V1 includes an agreed initial set of public/direct source adapters. Each remains independently enabled, rate-limited, and health-checked.

### ADR-009 — No authentication in V1; fixed local owner

**Decision:** V1 has no login. A fixed local owner context is used and `owner_id` scoping is kept in the data model.

**Why:** Personal, LAN-only use; authentication adds scope without value yet.

**Consequence:** Authentication is a future change and must be introduced before any multi-user or shared access. The app stays LAN-only.

### ADR-010 — Uploaded CVs are never stored

**Decision:** Uploaded documents are processed in memory (text extraction, optional AI use) and discarded. No document storage or retention policy exists.

**Why:** Minimises restricted personal data held at rest.

**Consequence:** Only metadata and user-reviewed source excerpts linked to accepted facts persist. Re-import requires a new upload.

### ADR-011 — PostgreSQL only, BIGSERIAL keys

**Decision:** PostgreSQL in all environments (no SQLite); primary keys are BIGSERIAL, foreign keys BIGINT.

**Why:** Test/production parity and a consistent convention across Innovation Ways projects.

**Consequence:** Integration tests use isolated PostgreSQL containers.

### ADR-012 — Sources are database-configured

**Decision:** Source URLs, rate limits and optional credentials live in the database, managed from the frontend, which also shows per-source status (last run, outcome, counts, error reason). Credentials are encrypted and write-only.

**Why:** Sources must be added and tuned without code changes.

**Consequence:** V1 starts with one source; the first source is selected from research (ODR-004).

### ADR-013 — Credential encryption key comes from the environment

**Decision:** The key used to encrypt stored credentials is supplied through an environment variable defined in an untracked `.env` file (never committed, never in the database). `.env.example` documents the variable name without a value.

**Why:** Simplest option that keeps the key out of the database for a single-user local deployment.

**Consequence:** Losing the key makes stored credentials unrecoverable (re-enter them). The key must be backed up separately from the database.

### ADR-014 — Primary key naming

**Decision:** Primary keys are BIGSERIAL named `{table_name}_id`; foreign keys reuse the referenced primary key's name. A bare `id` is never used.

**Why:** Unambiguous joins and API fields; consistent with other Innovation Ways projects.

**Consequence:** Applies to database columns, API path parameters and JSON fields.

### ADR-015 — Greenhouse Job Board API is the first source

**Decision:** The first V1 source type is the Greenhouse Job Board API (`boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`); Lever and Ashby follow as later adapters. A source is one company board, so the company/board-token list is user-editable configuration managed in the GUI. A board token is validated when added (HTTP 200 with a non-empty `jobs` array). Default polling is at most one run per board per day, using `If-None-Match`, bounded timeouts and backoff on 429/5xx.

**Why:** See research R-00169: public, unauthenticated, real results verified, `updated_at` for change detection, ETag support, full content in one call.

**Consequence:** Descriptions must be HTML-unescaped and sanitised during normalisation. Vendor terms still need review before public OSS release (ODR-007).

**Development seed:** The 14 verified board tokens from R-00169 may be kept as a development-only seed (never loaded by tests). Automated tests MUST stub the HTTP layer and use recorded synthetic responses; they MUST NOT read the development seed and MUST NOT perform real network requests to any job source (enforced by a test-time network block, so an accidental real call fails the test).

### ADR-016 — Repository

**Decision:** The project lives in the `iw-jobs-radar` repository. Work happens directly on `main` for now. The separate `cv` repository is never modified.

**Why:** Isolation from other projects; simplest workflow for a single developer.

**Consequence:** Branch/worktree workflows may be introduced later by a new ADR.

### ADR-017 — Separate worker process with a GUI-configurable schedule

**Decision:** Collection runs in a dedicated worker process (separate from the API), not inside the API process. The daily run time and IANA time zone are user settings stored in the database and editable in the GUI. Manual `Run now` requests and scheduled runs are executed by the same worker. External notifications are out of scope for V1; the in-app digest is the V1 notification surface.

**Why:** Source failures and long runs must not affect the API; runs must be idempotent and independently retryable per source (TR-5).

**Consequence:** Docker Compose runs at least `db`, `api`, `worker`; a database lock prevents duplicate runs. A dedicated launcher script (see ADR-018) manages all processes.

### ADR-018 — Dedicated development launcher

**Decision:** A launcher script at the repository root (modelled on the launcher of another Innovation Ways project) starts, stops, restarts, rebuilds, health-checks and tails logs of every service (database, API, worker, frontend), in interactive-menu and CLI-flag modes. CLI flags are the interface for AI agents; `--health` exits 0 only if everything is healthy.

**Why:** Several processes must be operated reliably by the developer and by agents.

**Consequence:** The launcher is part of the foundation work; its exact name and port choices are recorded in the implementation guide.

### ADR-019 — Environment-driven ports, frontend service in Compose, CI deferred

**Decision:** All host ports (API, frontend, PostgreSQL, worker health if any) are configurable per environment through the untracked `.env` file; `.env.example` documents the variable names with these development defaults: API `8100`, frontend `5180`, PostgreSQL `5440` (chosen so the project can run next to other local services; 8000, 5173, 5432, 5433 and 5435 are already used on the development machine). The Docker Compose file includes a `frontend` service that is **commented out**: in development the frontend runs outside containers (Vite dev server). CI (GitHub Actions) is deferred and will be added later by a new decision; quality gates run locally until then.

**Why:** Avoid port clashes on a shared development machine; keep the dev loop fast; avoid premature CI work.

**Consequence:** No port, URL or credential is hardcoded anywhere. TR-7.6 (CI execution) is deferred, not dropped.

### ADR-020 — Task-guide delivery order

**Decision:** Implementation follows a sequential task guide (not work items, for now) in this order: 0 foundation and launcher; 1 data contracts and migrations; 2 Greenhouse collection and sources screen; 3 manual profile and intent; 4 matching and inbox; 5 worker/scheduler and digest; 6 AI settings, CV import, Ollama; 7 company dossiers and market pulse; 8 hardening. This supersedes the increment order in document 09 where they differ; the task guide is authoritative.

**Why:** Real scored jobs become visible early.

**Consequence:** Work items (`iw-new-feature`) may be adopted later.

### ADR-021 — AI-first hybrid evaluation (amends ADR-004, ADR-005, ADR-007)

**Decision:** An LLM does the understanding work: it extracts structured attributes from each job (work mode, seniority, technologies, engagement type, role family, sector, …) and issues a per-dimension judgement (`match` / `mismatch` / `unknown`, strength, quoted evidence). These outputs are stored as immutable evidence together with provider, model, prompt-template version and timestamp. The final score is then computed **deterministically** from the stored judgements (weights, hard gates, sum) with no LLM in the final step. `unknown` still contributes zero. Changing model or prompt creates a *new* evaluation; older evaluations are kept and remain reproducible. There are no keyword-rule fallbacks.

**No-AI mode is reduced to a minimum:** without a configured LLM, collection, sources, inbox, history and company data still work, and jobs are shown as "not evaluated". No substitute scoring rules are built.

**Why:** The product's value is the LLM's comprehension of fit and company research; a parallel rule engine would be a second, weaker system to maintain. Storing judgements keeps the explainability and reproducibility goals of ADR-004.

**Consequence:** AI quality and availability now directly affect scoring completeness; evaluation is queued and retried by the worker (ADR-017). Prompts and extraction schemas are versioned artefacts. Privacy rules (consent, redaction, no silent local-to-cloud fallback) are unchanged; public job text is lower risk than profile/CV text.

### ADR-022 — Data model must support market-trend analysis from day one

**Decision:** The complete data model is built from the start: per-snapshot extracted attributes on a stable, versioned taxonomy (role families, canonical technology names), job lifecycle (first seen, last seen, closed), source provenance (where each job was found, original URL), the full description and responsibilities, and the profile/intent-relevance flag with the threshold used. Weekly aggregates over *relevant* jobs only are stored so that trends (for example change in demand for a technology or role family over a period) can be computed. History starts when collection starts; the UI must show the available period. Trend screens are delivered in the task for company dossiers and market pulse; the data is captured from the first collection.

**Why:** Historical data cannot be reconstructed later.

**Consequence:** Taxonomy changes must be versioned so older counts remain interpretable.

### ADR-023 — Cross-source duplicate handling (principle; details in the domain design document)

**Decision:** Each source listing is kept as its own `JobPosting` (provenance is never discarded). Listings that describe the same real opportunity are linked to one canonical opportunity record using the same company, similar normalised title, compatible location, similar description (text similarity, optionally local embeddings) and close dates. High-confidence matches are linked automatically; medium-confidence matches are flagged as "possible duplicate" for the user; links are reversible and never destructive. The inbox shows one item per opportunity, listing every site where it was seen. Postings that differ by location (e.g. the same title in several cities) are distinct opportunities unless the user's intent ignores location.

**Why:** Prevents repeated review of the same role while keeping evidence of every source.

**Consequence:** Requires the Company entity and a similarity design; thresholds are fixed in the domain design document and tested with synthetic fixtures. The inbox item is keyed by opportunity (ADR-028).

### ADR-024 — User-adjustable relative scoring weights

**Decision:** Each scoring dimension has a user-adjustable weight stored on the intent revision, initialised to the policy default. Weights are relative and normalised to the 0–100 score. Changing weights creates a new intent revision and never alters past evaluations; an explicit "re-score existing jobs" action recomputes from the stored AI judgements without new AI calls.

**Why:** Different users value dimensions differently (for example compensation over sector).

**Consequence:** A heavily weighted dimension that is often `unknown` lowers scores for jobs where it is unknown; the UI shows a live impact preview so this is visible before saving.

### ADR-025 — Company enrichment from free public sources

**Decision:** Company facts may be enriched from free public APIs (research R-00171): Wikidata (primary), Wikipedia summary with attribution, GLEIF, and GitHub organisation data. A match is accepted only when the official-website domain equals the known board/careers domain, or the user confirms it. Every enriched fact stores source, retrieval date and licence.

**Why:** Job boards give only a company name.

**Consequence:** Coverage for small companies will be partial; the dossier shows unknown rather than guessing. Keyed registries are optional later sources.

### ADR-026 — Three-state stance model and revised scoring criteria

**Status:** accepted by the owner on 2026-10-08, based on research R-00172 and the Profile & intent mock-up. Applied to FR-3, FR-5, UC-03, the API contract and LLD §4; details in document 13.

**Proposal:**
1. Every option in the Search Intent (role families, work arrangements, engagement types, seniority levels, sectors, employer types) has a stance: **Preferred**, **Acceptable** or **Rejected**. Rejected acts as a hard gate (job becomes Not recommended); Preferred and Acceptable contribute different strengths to the score.
2. Work arrangement and location are one criterion: each arrangement (remote, hybrid, on-site) has its own place rule (remote: eligible regions and time-zone tolerance; hybrid/on-site: distance from a base place). A remote job restricted to ineligible regions is Rejected.
3. Compensation is type-aware: annual gross salary for employees, day rate for contractors/freelancers, each with minimum and target, plus an option to reject jobs whose stated pay is below the minimum. Unstated pay stays `unknown` (ADR-005).
4. Scoring dimensions become: Role & responsibilities 25, Skills & technology 15, Work arrangement & location 15, Engagement & contract terms 10, Compensation 10, Seniority & experience 8, Domain & sector 10, Company profile 7 (total 100), plus optional dimensions Benefits & flexibility and Qualifications with default weight 0.
5. Languages the user can work in are a gate for postings that require other languages. Date posted and applicant count are sort/filter options, not scoring dimensions.
6. Dimension weights set to 0 are shown greyed as excluded from the score.

**Why:** The eight original dimensions merge or miss criteria that job seekers use (R-00172 F3, F4, F5, F9).

**Open design question (for the domain design document):** categorical dimensions (work arrangement, engagement, seniority, sector, employer type) can be matched deterministically from LLM-extracted attributes, so the LLM would extract attributes once per job (independent of the intent) and only fuzzy dimensions (role and skills similarity) need profile-dependent judgements. This reduces AI calls and makes re-scoring after intent changes free of AI calls.

### ADR-027 — Two-stage AI with deterministic evaluation (refines ADR-021)

**Status:** accepted by the owner on 2026-10-08 (domain design document, section 6).

**Proposal:** The AI extracts structured attributes from each job once per snapshot, **independent of any intent or profile** (evidence quotes mandatory and verified). Categorical dimensions are then scored deterministically from those attributes and the intent's stances. The only profile-dependent AI step is a cached **skill-equivalence judgement** per skill pair. Evaluation itself therefore makes no AI call except for never-judged skill pairs, and re-scoring after changing weights or stances needs no AI call.

**Why:** Lower AI cost and latency, full reproducibility, and one extraction serves every intent and profile.

**Consequence:** ADR-021's "per-dimension judgement with quoted evidence" is replaced by "extracted attributes with quoted evidence plus cached skill-pair judgements". Privacy rules are unchanged: public job text goes to the AI; the profile is only used locally for skill-pair names.

### ADR-028 — Domain design decisions (document 13)

**Decision:** The owner accepted document 13 decisions D1–D10: offline GeoNames-based gazetteer (data CC BY 4.0, attribution shown in the app); same-currency pay comparison only in V1 with currency conversion as a pending improvement; local embeddings for duplicate detection with a shingle fallback; stance strengths 1.0/0.5 and quality thresholds 0.75/0.25 as initial constants; unlisted role families and sectors score 0 without a gate; the initial taxonomies; inbox items keyed by opportunity; ESCO deferred (nullable); employee pay entered as linked monthly and annual fields with a 12 or 14 payments choice (annual canonical, contractors by day rate only); and ADR-027.

**Why:** Closes the design gaps needed to start implementation.

**Consequence:** Deferred improvements are tracked in document 13, section 12.

### ADR-029 — Repository layout and module boundaries

**Decision:** Single repository with `backend/` (Python package `jobs_radar` under `src/`; `tests/unit`, `tests/integration`, `tests/e2e`; `alembic/`), `frontend/`, `docker-compose.yml`, `docker-compose.dev.yml`, `.env.example`, a root launcher `jobs-radar.sh` and a root `Makefile` that delegates to backend and frontend tooling. Backend packages: `api` (routes), `schemas`, `services`, `repositories`, `db`, `domain` (enums, value objects, the pure matching engine), `adapters` (`sources`, `providers`, `enrichment`), `worker`, `core` (settings, logging, security helpers). Import-linter contracts: `api → services → repositories → db`; `domain` imports nothing from the other packages; the matching engine imports only `domain`; `adapters` import only `domain` and `schemas`, never `repositories` or `db`; `worker` may import `services`.

**Why:** Enforces the architectural invariants of the HLD (adapters never touch the database; matching is pure) mechanically.

**Consequence:** Any new package must be added to the import-linter contracts in the same change.

### ADR-030 — Database access and conventions

**Decision:** PostgreSQL 18 (image `postgres:18`). SQLAlchemy 2.0 async ORM with psycopg 3 (`postgresql+psycopg://`); Alembic migrations run synchronously with the same driver. Primary keys are `BIGINT GENERATED BY DEFAULT AS IDENTITY` named `{table_name}_id` — the modern PostgreSQL form of the BIGSERIAL rule of ADR-011/ADR-014 (accepted by the owner on 2026-10-08). JSON payloads use `JSONB` validated by Pydantic models carrying a `schema_version`. Mutable rows carry an integer `version` for optimistic concurrency. Append-only tables (profile and intent revisions, snapshots, extractions, evaluations, score dimensions, inbox events) are protected by database triggers that reject `UPDATE` and `DELETE`; user-requested deletion (UC-08) uses a dedicated, audited procedure that is the only path allowed to bypass the trigger.

**Why:** Immutability is a core invariant and should not rely on application code alone.

**Consequence:** Migrations create the triggers; integration tests prove them.

### ADR-031 — Worker and scheduler mechanism (implements ADR-017)

**Decision:** The worker is a separate process (`python -m jobs_radar.worker`) with a single asyncio loop that polls the database every `JOBS_RADAR_WORKER_POLL_SECONDS` (default 15). It (1) reads `schedule_setting` and creates a `collection_run` for the next due time using `zoneinfo` (unique on `(owner_id, scheduled_for)` so a run is created once), (2) claims queued runs with `SELECT … FOR UPDATE SKIP LOCKED` and executes sources one after another with per-source rate limits, (3) claims `job_extraction` rows in `pending` state with bounded concurrency (`JOBS_RADAR_EXTRACTION_CONCURRENCY`, default 1), and (4) writes a heartbeat used by `/readyz` and the Sources screen. A PostgreSQL advisory lock guarantees a single active worker. Manual "Run now" inserts a queued `collection_run`; the API never executes collection. No Celery, Redis or APScheduler.

**Why:** Simplest mechanism that satisfies idempotent, observable, independently retryable runs (TR-5) with GUI-editable schedule and no extra infrastructure.

**Consequence:** Schedule changes take effect within one poll interval; a stuck run is detected by heartbeat age and marked failed on worker restart.

### ADR-032 — Configuration

**Decision:** `pydantic-settings` with prefix `JOBS_RADAR_` and `__` for nesting, read from environment variables; `.env` (untracked) is loaded by the launcher and Docker Compose. `.env.example` lists every variable without secrets. Initial variables: `JOBS_RADAR_ENV` (`dev`, `test`, `prod`), `JOBS_RADAR_API_PORT` (8100), `JOBS_RADAR_API_BIND` (default `127.0.0.1`), `JOBS_RADAR_FRONTEND_PORT` (5180), `JOBS_RADAR_DB_PORT` (5440), `JOBS_RADAR_DB_BIND` (address the database port is published on, default `127.0.0.1`), `JOBS_RADAR_DB_NAME`, `JOBS_RADAR_DB_USER`, `JOBS_RADAR_DB_PASSWORD`, `JOBS_RADAR_CREDENTIAL_KEY`, `JOBS_RADAR_OLLAMA_URL` (default `http://host.docker.internal:11434`), `JOBS_RADAR_ALLOW_LOCAL_PROVIDERS`, `JOBS_RADAR_WORKER_POLL_SECONDS`, `JOBS_RADAR_WORKER_HEARTBEAT_MAX_AGE_SECONDS`, `JOBS_RADAR_EXTRACTION_CONCURRENCY`, `JOBS_RADAR_LOG_LEVEL`, `JOBS_RADAR_CORS_ORIGINS`, `JOBS_RADAR_FRONTEND_ALLOWED_HOSTS` (host names the Vite dev server accepts). The launcher can generate a first `.env` with a random database password and credential key. Every new variable is added to `.env.example` and to the configuration documentation in the same change.

**Why:** One place for everything environment-specific (ADR-019), no hardcoded ports or secrets.

**Consequence:** The API and worker refuse to start in `test` against a non-test database; the default API bind is loopback because there is no authentication (ADR-009): LAN exposure is an explicit choice (`JOBS_RADAR_API_BIND=0.0.0.0`).

### ADR-033 — Credential encryption

**Decision:** Fernet (`cryptography`) with the key from `JOBS_RADAR_CREDENTIAL_KEY`; ciphertext stored in a dedicated column, never in JSON payloads; `MultiFernet`-ready for future key rotation. API and UI only ever see a status (`saved`, `none`) and the last-updated time.

**Why:** Meets TR-4 with a small, well-reviewed primitive (ADR-013).

**Consequence:** Losing the key makes stored credentials unrecoverable; they must be re-entered.

### ADR-034 — Tooling and dependency policy

**Decision:** Backend: Python 3.13 managed by `uv` (lockfile committed); FastAPI + Uvicorn, SQLAlchemy 2, Alembic, psycopg 3, Pydantic 2, pydantic-settings, httpx, structlog, tzdata, `nh3` (HTML sanitising), BeautifulSoup + lxml (HTML to text), `pypdf` and `python-docx` (CV text extraction), `rapidfuzz`, `geonamescache`, `cryptography`, `python-multipart`. Dev tools: pytest, pytest-asyncio, pytest-cov, hypothesis, testcontainers, respx, pytest-socket, ruff, mypy, import-linter, bandit, semgrep, deptry, vulture. Frontend: Node 22 LTS with pnpm via corepack (version pinned in `packageManager`), Vite, React, TypeScript (strict), React Router, TanStack Query, React Hook Form + Zod, Tailwind CSS v4, shadcn/ui on Radix, lucide-react, Inter self-hosted through `@fontsource-variable/inter` (no CDN), `openapi-typescript` + `openapi-fetch` for the generated API client, Vitest + Testing Library, Playwright, ESLint, Prettier; sparklines are a small hand-written SVG component (no chart library in V1). **No AGPL or proprietary runtime dependency** (for example PyMuPDF is excluded); a licence-check gate enforces it for both ecosystems. GPL-family questions are covered by ODR-007.

**Why:** Meets the stack in TR-1 and the licence rule used across Innovation Ways projects.

**Consequence:** Versions are those current at scaffolding time, recorded in the lockfiles; upgrades are separate commits.

### ADR-035 — Outbound HTTP, SSRF and test isolation

**Decision:** All outbound calls use one httpx async client factory with timeouts (connect 5 s, total 30 s), a maximum response size, a User-Agent identifying the application, bounded redirects each re-validated, and a shared `UrlGuard` (HTTPS by default; block loopback, link-local and metadata addresses; private/loopback targets only when `JOBS_RADAR_ALLOW_LOCAL_PROVIDERS` is on and the host is explicitly configured, for example the local Ollama). Sources have a per-source token-bucket rate limit, `Retry-After`-aware backoff on 429/5xx, no unbounded retry loops, and conditional requests (`If-None-Match`) with the ETag stored per board. In tests, HTTP is stubbed with `respx` and `pytest-socket` blocks all sockets except loopback and the Docker unix socket, so an accidental real request fails the test (ADR-015).

**Why:** One audited path for every network call (TR-4.5, TR-5.3).

**Consequence:** No adapter creates its own HTTP client.

### ADR-036 — Logging and health

**Decision:** `structlog` JSON logs to stdout with a `request_id` (from `X-Request-ID` or generated) bound per request and per worker task; a redaction processor removes known secret keys and never logs request bodies, CV text, descriptions or prompts. `/healthz` reports process liveness; `/readyz` checks the database and the worker heartbeat age and exposes no personal data.

**Why:** TR-5.4, TR-5.5 and the privacy rules.

**Consequence:** Log redaction has a dedicated test.

### ADR-037 — API implementation conventions

**Decision:** Pydantic models use `extra="forbid"` and strict enums; errors use the envelope of document 07 through exception handlers; list endpoints use opaque keyset cursors; the generated OpenAPI document is committed as a snapshot and a test fails on unreviewed changes; the frontend client is regenerated from it with a single command; CORS allows only the configured frontend origin.

**Why:** Keeps the contract explicit and the frontend in sync.

**Consequence:** Contract changes require updating the snapshot deliberately.

### ADR-038 — Docker Compose runtime

**Decision:** `docker-compose.yml` defines `db` (bound to 127.0.0.1 only, named volume, healthcheck), `api` and `worker` (built from one backend image) and a commented `frontend` service. `docker-compose.dev.yml` overrides `api` and `worker` with bind-mounted sources and auto-reload. Containers reach the host Ollama through `host.docker.internal` (`extra_hosts: host-gateway`). Ports and credentials come from `.env`. In development the frontend runs outside containers (ADR-019).

**Why:** Matches HLD section 5 and ADR-017/019.

**Consequence:** The launcher (ADR-018) wraps Compose, the frontend dev server and health checks.

### ADR-039 — Amend ADR-020: move the extraction pipeline earlier

**Status:** accepted by the owner on 2026-10-08.

**Proposal:** ADR-020 places all AI work in task 6, but with ADR-021/027 no real job can be scored without AI extraction, so "real scored jobs after task 4" would not hold. Move the **extraction provider interface, a minimal Ollama adapter, the `extract-v1` prompt, evidence verification and the worker extraction queue** into task 4 (matching and inbox). Task 6 keeps AI & Privacy settings, cloud and compatible providers, consent and redaction, credentials and CV import.

**Why:** Real scored jobs appear as soon as the inbox exists, using the local Ollama already available.

**Consequence:** Task 4 grows; task 6 shrinks. The task guide (document 14) already follows this order.

### ADR-040 — Decisions taken while implementing T0

**Decision:** (1) The secret scan is gitleaks run from a pinned container image (`make secret-scan`). (2) Licence gates are in-repo tools: `python -m jobs_radar.tools.check_licenses` for the backend (fails on AGPL, SSPL and proprietary; reports LGPL and unknown for review) and `license-checker-rseidelsohn` for the frontend. `psycopg` 3 is LGPL-3.0 and is accepted as an unmodified library dependency. (3) The application is served at the root path `/`. (4) `pnpm` is pinned to 11.28.5 through corepack because `pnpm@latest` (12) failed to run through corepack in this environment. (5) `httpx2` is a development dependency only, because Starlette 1.7's `TestClient` requires it; production HTTP clients keep using `httpx` so that `respx` works. (6) ESLint and Prettier are kept (ADR-034) instead of the Vite template's oxlint. (7) During development Vite proxies `/api`, `/healthz` and `/readyz` to the API so the browser always calls the same origin. (8) Only the indigo accent is implemented; the other two accent options from the mock-up are dropped until a setting is requested. (9) Dark-mode semantic colours use the calmer values approved in the mock-up review.

**Why:** Closes the T0 "ask before starting" points with the recommended defaults and records the environment findings.

**Consequence:** Any of these can be revisited by a new ADR.

### ADR-041 — Decisions taken while implementing T1 (data contracts)

**Decision:**
1. **Owner table.** A real `owner` table (seeded with one local owner, `owner_id = 1`) is the target of every `owner_id` foreign key, so adding users later needs no data migration (ADR-009).
2. **Conditional immutability.** `job_extraction` rows are queued as `pending` and updated exactly once to `succeeded` or `failed`; from then on they are immutable (a second trigger function). The other immutable tables (profile and intent revisions, evidence, job snapshots, change events, evaluations, score dimensions, inbox events, source run results, audit events) reject every UPDATE and DELETE. `collection_run` is mutable (its status changes); its per-source `source_run_result` rows are append-only. This refines document 13 section 6.3, which said extraction rows are always immutable.
3. **Audited deletion.** `delete_career_profile` is the only code that bypasses the triggers; it switches the bypass on and off explicitly and records an audit event with counts and ids only. It covers the profile, its revisions, intents, evaluations, proposals and trend rows; document metadata, evidence and inbox state follow in task T6.
4. **Foreign-key naming.** Foreign keys reuse the referenced primary key name (ADR-014). Where a table references the same table twice or in a named role, a role name is unavoidable and allowed: `current_profile_revision_id`, `current_intent_revision_id`, `primary_job_posting_id`, `from_job_snapshot_id` / `to_job_snapshot_id`, `skill_id_a` / `skill_id_b`, `replaced_by_taxonomy_term_id`, `introduced_in_taxonomy_version_id`.
5. **Circular references** (profile ↔ current revision, intent ↔ current revision) are nullable foreign keys added after both tables exist.
6. **Taxonomy versions** are rows in `taxonomy_version`; terms and extractions reference them.
7. **Enumerations** are stored as text with named CHECK constraints (not PostgreSQL enum types) so adding a value is a one-line migration; constraint names stay within PostgreSQL's 63-character limit.
8. **Cascades** follow ownership: deleting a profile cascades to its revisions, intents, proposals and the evaluations and trend rows derived from them; job, company and source data are never cascaded.
9. **Frozen migration inputs.** The SQL constants in `db/triggers.py` and the seed in `domain/taxonomy_seed.py` are imported by migrations and must not be edited; changes need a new migration.
10. **API request/response models** are defined together with their endpoints (T3 onwards), not in T1; T1 delivers the domain contracts (profile facts, intent, normalised job, extraction output).
11. **Generated documentation.** `docs/database/schema.md` is generated from the models (`make docs-schema`) and a test fails when it is stale.
12. **Settings** also read the repository-root `.env` when run from `backend/`, and `JOBS_RADAR_FRONTEND_ALLOWED_HOSTS` is a declared setting (strict mode rejects unknown keys).

**Why:** Closes the details the design left open while keeping every accepted decision.

**Consequence:** Later tasks build on these tables and constraints without schema surprises.

### ADR-042 — Decisions taken while implementing T2 (Greenhouse collection and Sources screen)

**Status:** approved by the owner (2026-10-08).

**Decision:**
1. **Run scope.** `collection_run` has a nullable `source_configuration_id`: set for a manual run of one source, empty for a run of all enabled sources. A disabled source can still be run by hand.
2. **Closing rule.** A posting is closed only after two consecutive *successful* runs of its source without it (absent now and not seen since the previous successful run began). A failed run closes nothing and does not count as a miss; a posting that reappears is reopened and counted as updated. A 304 refreshes `last_seen_at` of every open posting.
3. **Change detection.** Material fields (title, description text, locations, apply URL) are hashed after normalisation (whitespace, location order, tracking parameters ignored); only a material change adds a snapshot and a change event. The source's `updated_at` is stored but is not a change input.
4. **Collected jobs state only what the source states.** Work mode, seniority, skills, pay and the other attributes are `unknown` until AI extraction (T4); nothing is guessed (ADR-005).
5. **Politeness defaults.** Per-source rate limit 6 requests per minute (configurable 1 to 60), at most 3 attempts on 429/5xx with `Retry-After` honoured and capped at 60 s, conditional requests with the stored ETag, 25 MB response cap, 30 s total timeout.
6. **Adding a board validates it** (board exists, answer well formed) and creates or reuses the company by normalised name; an invalid or unknown token is refused (422 with an error class) and a source outage returns 503; nothing is saved in either case.
7. **Executor.** Until the worker exists (T5), the API runs queued runs as background tasks of its own process (`RunExecutor`). On start it marks runs left queued or running by a previous process as failed (`interrupted`); the API still starts if the database is down. T5 moves both responsibilities to the worker.
8. **Failure isolation.** Each source is fetched outside any database transaction and stored in its own short transaction; an unexpected adapter or storage error is recorded as class `unknown` with a generic message (no addresses or payloads) and never stops the other sources. A run is `succeeded`, `partial` or `failed` accordingly.
9. **Development seed.** `make seed-dev-sources` adds the 14 boards of research R-00169 as **disabled** sources with curated names, makes no network request, refuses to run outside `JOBS_RADAR_ENV=dev`, and is never used by tests.
10. **Sources screen** also has Enable/Disable per board (optimistic concurrency), needed because the seeded boards start disabled. The schedule card is read-only until T5.

**Why:** Closes details the design left open while keeping every accepted decision (ADR-005, ADR-012, ADR-015, ADR-031).

**Consequence:** T3 onwards can rely on collected postings and snapshots; T4 adds extraction on top of the same snapshots; T5 replaces the in-process executor.

**Verified manually (2026-10-08):** one real run of the `anthropic` board stored 646 postings and snapshots (HTTP 200, 2.6 s) with no HTML left in descriptions; a second run answered 304 in 0.3 s with no duplicates; an unknown token was refused with class `not_found` and a malformed token with class `configuration`, saving nothing.

### ADR-043 — Decisions taken while implementing T3 (manual profile and search intent)

**Status:** approved by the owner (2026-10-08).

**Decision:**
1. **API additions to document 07** (it listed no way to edit a profile by hand, and the interface needs vocabularies and places): `PUT /profiles/{career_profile_id}` (save as the next revision; `expected_current_revision` is `null` for the first one), `POST /profiles/{id}/revisions/{profile_revision_id}/restore` and `POST /intents/{id}/revisions/{intent_revision_id}/restore` (restore as a new revision), `GET /intents/{id}/revisions/{intent_revision_id}`, `GET /taxonomy` and `GET /locations/search`. Document 07 is updated and marks them.
2. **Revision rules.** A save whose content equals the current revision creates nothing and answers `created: false`; a stale `expected_current_revision` is `409` even when nothing changed; restoring an old revision appends a new one ("Restored revision N") and never rewrites history.
3. **Provenance.** Profile items (skills, roles, education, certifications) that did not change keep their provenance; new or edited items get manual provenance with the time of acceptance. Skills are typed by name and resolved to canonical skills by alias or name ignoring case and punctuation (`Node.js` = `node js`; `+` and `#` are kept); a new skill defaults to kind `technology`.
4. **Intent validation.** Besides the schema rules, an intent is checked against the live taxonomy: every key must exist and the closed groups (work arrangements, engagement types, seniority levels, employer types) must list every term. Role families and sectors are open groups: an option may have no opinion (not listed); role families may not be empty.
5. **Weights screen.** The T3 screen shows each dimension's effective share, greyed zero weights, optional criteria and the worked example; the **impact preview** on current jobs (`POST /intents/{id}/weights-preview`) is approved but implemented in T4, when evaluations exist to recompute.
6. **Frontend drafts** are plain React state compared with the saved revision, with targeted validation functions mirroring the server rules (the server stays the authority and answers 422). React Hook Form and Zod remain for flat forms (settings, T7). Panels stay mounted when switching tabs and the owner is asked before unsaved edits would be lost.
7. **Education and certifications** are kept unchanged by manual saves and are not editable until the CV import review (T6).
8. **Locations** are looked up offline with `geonamescache` (MIT code, GeoNames data CC BY 4.0, credited in the sidebar) with the rules of document 13 section 6.2: exact primary name first, country from the parameter or the text, a name present in several countries stays unresolved, most populous city within one country.
9. **Export** (`GET /profiles/{id}/export`) contains the profile title, the current facts, privacy settings and the current definition of each intent; it never contains credentials.

**Why:** Closes gaps in document 07 and keeps every accepted decision (ADR-003 canonical profile, ADR-005 no guessing, ADR-026 stances).

**Consequence:** T4 can rely on stored profile and intent revisions and adds the weights impact preview; T6 adds import review and profile deletion in the interface.

**Verified manually (2026-10-08):** with the stack running, the document 13 example intent was created through the API (revision 1), a weight change created revision 2, History listed both, a stale save returned `409`, the offline search found `Setúbal, Portugal`, and the throw-away profile was then removed with the audited deletion.

### ADR-044 — Decisions taken while implementing T4 (extraction, matching, duplicates and inbox)

**Status:** approved by the owner (2026-10-08).

**Decision:**
1. **Defaults chosen by the owner:** extraction model `qwen3:8b`, embeddings `qwen3-embedding:8b`, descriptions truncated at 12,000 characters (flagged `truncated`). They are settings (`JOBS_RADAR_EXTRACTION_MODEL`, `JOBS_RADAR_EMBEDDING_MODEL`, `JOBS_RADAR_EXTRACTION_MAX_CHARS`) until the AI & privacy screen (T6) stores them. **AI is opt-in:** `JOBS_RADAR_EXTRACTION_ENABLED` is off by default (ADR-004); jobs are then collected, grouped and listed as "not evaluated". A local Ollama is reachable only when `JOBS_RADAR_ALLOW_LOCAL_PROVIDERS` is on and the host is the configured one; that host may use plain HTTP and `host.docker.internal` (the URL guard still refuses link-local addresses).
2. **Extraction robustness.** Small models bend the output contract (a value on an `unknown` attribute, no quote, a key instead of a quote). The answer is therefore salvaged field by field: attributes outside the contract become `unknown` (noted in `unverified`), invalid list items are dropped, keys outside the taxonomy are removed (`dropped_keys`), and only an answer that is not an extraction is repaired once and then failed. Evidence is still checked verbatim against the posting. Real runs with `qwen3:8b` took 6 to 16 seconds per job.
3. **Failure policy.** An unreachable provider, a missing model, a refused address or a 5xx leaves the job waiting without using an attempt; timeouts and unusable answers use an attempt (at most 3, then `failed`). A batch ends at the first unreachable-provider error and is time-bounded so the worker heartbeat stays fresh.
4. **Skills.** A job skill mention that matches no alias creates the skill at once and an *accepted* `skill_candidate` row (document 13 said "queued for review"; review and merging come later), so the equivalence judgement always has a skill to compare. Pair judgements are one batched call per job skill, cached once per pair; names the model invents are ignored; a failing provider leaves pairs unjudged; a judgement by the owner is never overwritten.
5. **Matching `matching-v1`** is a pure module with exact fraction arithmetic; contributions are rounded to one decimal half up and the score is the rounded sum. The time-zone tolerance of document 13 is **not applied** because the extraction carries no time-zone band (remote eligibility uses region groups EU, EEA, EUROPE, UK, WORLD and country codes; unreadable or unstated regions give the 0.8 risk factor). Skill coverage uses 1.0 for a held skill, 0.5 equivalent, 0.25 related; the profile level is not compared because jobs carry no per-skill level.
6. **Evaluations are append-only and new weights apply from now on.** New jobs are scored by the worker for every enabled intent; existing jobs are scored again only on request (`POST /intents/{id}/rescore`, no model call). The weights impact preview endpoint stays pending.
7. **Duplicates `dedup-v1`.** Only listings of the same company on *different* sources are compared (listings of one board are never linked, which also avoids comparing every pair of a large board). A `possible` link groups the listing under the opportunity but flags it for the owner (confirm or reject); rejecting gives the listing its own opportunity and keeps the rejected link as history. The primary listing is the employer's ATS (Greenhouse, Lever, Ashby), then the earliest. Description similarity uses local embeddings when available and five-word shingles otherwise.
8. **Inbox.** One item per opportunity; every open opportunity is surfaced, scored or not; restore from `applied` clears the recorded application; opening an already read item records nothing; shortlisting twice is a validation error. Closed opportunities are hidden unless applied. A material source change moves eligible items to `updated_unread`.
9. **API additions to document 07:** `GET /evaluations/{id}`, `POST /jobs/{id}/evaluations` (no model call), `POST /intents/{id}/rescore`, the `q` text search of `GET /inbox`, and `POST /opportunity-links/{id}/confirm|reject`.

10. **Found while running real jobs (qwen3:8b on 24 jobs of the `anthropic` board).** A model can fall into a repetition loop, so the Ollama request caps the output (`num_predict` 4,096 tokens); without it one job blocked a batch until the 180-second timeout. A board joins several places in one string ("New York City, NY; San Francisco, CA | Remote"), so places are split on `;` and `|`, and `City, XX` with a US state code is read as that state before a country code. Places are resolved when a job is **scored** (offline, cheap), from the extracted places or else the source's own, not trusted from the stored extraction, so gazetteer improvements also apply to old extractions.

**Why:** Closes details the design left open while keeping every accepted decision (ADR-005, ADR-021, ADR-023, ADR-027, ADR-039).

**Consequence:** T5 moves scheduling and the collection pipeline to the worker; T6 adds the AI & privacy screen and CV import; the weights impact preview and the review of auto-created skills remain open.

**Verified manually (2026-10-08):** with the local stack and Ollama, 30 real jobs were extracted (about 10 s each, no truncation), scored for a synthetic profile and intent, and shown in the Inbox with evidence per dimension; a weight change plus `POST /intents/{id}/rescore` re-scored all 30 with no model call (a second call re-scored none); the synthetic profile was then removed with the audited deletion. The 646 collected jobs were already grouped into 646 opportunities and listed as not evaluated by the worker with AI off. A second source for the same job was not available, so cross-source linking was verified by tests only.

### ADR-045 — Decisions taken while implementing T5 (worker, schedule and daily digest)

**Status:** approved by the owner (2026-10-08).

**Decision:**
1. **Defaults chosen by the owner:** the daily run is at **07:30 Europe/Lisbon**; a run still running after **30 minutes** is considered stuck. The schedule is created **disabled**: nothing contacts a source unattended until the owner turns it on in the Sources screen.
2. **Single active worker.** The worker holds a PostgreSQL advisory lock on a dedicated connection; a second worker stays on standby (no heartbeat, no work) and takes over when the lock is released, including when the first process dies.
3. **Scheduled runs.** One `collection_run` per occurrence, unique on `(owner_id, scheduled_for)`, so any number of workers create it once. Wall-clock time follows daylight saving: a time that does not exist that day runs just after the gap, a time that happens twice runs the first time only. A run is created only if its time is not older than 12 hours (catch-up after downtime), is not older than the last save of the schedule (saving 07:30 at 10:00 does not run at once) and at least one source is enabled.
4. **Recovery.** When a worker becomes active, runs left `running` by a dead process fail as `interrupted`; queued runs survive and run. An interrupted *scheduled* run is retried once as a new run; interrupted manual runs are not. Runs running longer than 30 minutes fail as `stuck` (same retry rule). A failed run never closes postings (ADR-042).
5. **The API no longer runs collection.** The in-process `RunExecutor` and the start-up cleanup in the API are removed; manual runs are queued and executed by the worker, which reports progress after every source so the heartbeat stays fresh.
6. **Digest** (`GET /digests/daily`, in-app only, last 24 hours): new *recommended* opportunities first seen in the window with a fit at or above the intent's alert threshold (default 65 without an intent), still reviewable (not ignored, archived or applied); shortlisted jobs with a material change in the window and the changed fields; enabled sources whose last run failed, that never ran, or with no success for 48 hours.
7. **API additions to document 07:** `GET` and `PUT /settings/schedule` (optimistic `expected_version`, IANA time zone validated, `next_run_at` and its local rendering) and `GET /digests/daily`. Frontend: editable schedule card, recent runs, Today screen and navigation badges.

**Why:** Closes the details ADR-017 and ADR-031 left open while keeping unattended behaviour opt-in.

**Consequence:** A schedule change reaches the worker within one poll interval (15 s). The dev worker image must be rebuilt after pulling this change.

**Verified manually (2026-10-08):** with the local stack, a schedule set three minutes ahead created and ran the scheduled run unattended (succeeded); a scheduled run left `running` was failed as `interrupted` when the worker restarted and was retried by a new run that succeeded. Killing the worker mid-run was covered by tests only (a real run finished in seconds). The schedule was switched off again afterwards.

### ADR-046 — Decisions taken while implementing T6 (AI & privacy settings and CV import)

**Status:** approved by the owner (2026-10-08).

**Decision:**
1. **The database decides.** The AI connection stored in `provider_connection` (managed in the AI & privacy screen) decides what the worker and the CV import use; the worker reads it on every iteration, so a change applies without a restart. The environment (`JOBS_RADAR_EXTRACTION_ENABLED`, model, Ollama URL) only **seeds** the first local connection, once, on the first read of `GET /settings/ai`. Default is **No AI**.
2. **Two uses, one rule.** A connection can be chosen for **CV import** (`is_active`, any type) and a **local** connection for **job analysis** (`use_for_jobs`, Ollama only). Public job text is never sent to a remote provider; a remote connection can only import CVs. Choosing a remote connection needs its credential saved and a model; there is no automatic fallback from local to remote.
3. **Providers.** Local Ollama and one OpenAI-compatible adapter (`/chat/completions` with `response_format: json_schema`, `/models` for discovery) serve OpenAI, MiniMax and any compatible server; `openai` has a default endpoint, `minimax` and `compatible` need one. Remote endpoints are validated with the SSRF guard when saved and on every call (HTTPS, public addresses); the local endpoint can only be the one configured for the deployment and needs `JOBS_RADAR_ALLOW_LOCAL_PROVIDERS`. A provider that cannot list models still works with a typed model id.
4. **Credentials** are encrypted with Fernet (`JOBS_RADAR_CREDENTIAL_KEY`, new dependency `cryptography`), accepted only by write endpoints, never returned, logged or exported; the API shows `credential_status: saved | none`. Without a valid key, storing a credential is refused (503).
5. **Privacy.** New table `privacy_setting` (one row per owner, `redact_contact_details` on by default). A remote call needs **consent for that connection and model, per CV**, recorded on the proposal (`consent_json`: provider, model, location, content category, purpose, redaction, time; no content, no credential). Redaction (`contact-v1`) replaces e-mails, phone numbers and links; names and places stay (they are needed to read a CV). Turning redaction off is allowed and recorded.
6. **CV handling (ADR-010).** Upload is validated by content (PDF, `.docx`, `.txt`, `.md`; 5 MB, 50 pages, zip-bomb guard), extracted in memory with `pypdf` and `python-docx` (new dependencies) and the original is dropped; a PDF without text is `needs_ocr`. Only metadata is stored. Because upload and proposal generation are two calls, the **extracted text is held in a process-local store for 30 minutes (at most 5 documents)**, never on disk or in the database, and is discarded when proposals are created. Uploads are kept in memory by raising Starlette's spool limit above the file limit. A restart or expiry asks for a new upload.
7. **Proposals and review.** The model returns `{items: [{path, value, excerpt, confidence}]}`; every item is validated on its own (`profile-import-v1`), wrappers and grouped lists that small models produce are unwrapped, an excerpt must occur verbatim in the text or it is dropped and the confidence capped at 0.5. Review (`POST /profiles/{id}/reviews`) applies accept / edit / reject / defer atomically in one savepoint: accepted and edited items become revision N+1 with `origin = document` provenance and an `evidence` row (document, excerpt, confidence); rejected and deferred items stay as audit data and never reach a revision; a first revision needs headline, base location and years of experience; a place is resolved offline (GeoNames) or must be edited. Deferred items can be decided later.
8. **Export and deletion (UC-08).** The profile export adds every profile and intent revision, document metadata, proposals with their review state and the owner's inbox decisions (no credential, provider setup, CV or CV text) and records an audit event with counts. `DELETE /profiles/{id}?confirm=<exact title>` removes the profile, its evidence and the documents no other profile's proposal uses, through the audited path; inbox decisions belong to job opportunities and stay.
9. **API additions to document 07:** `POST /settings/ai/connections`, `DELETE /settings/ai/connections/{id}`, `PUT /settings/ai/import-connection`, `PUT /settings/ai/jobs-connection`, `DELETE /profiles/{id}`; `GET /profiles/{id}/export` gains the history sections. Migrations 0004 (`privacy_setting`, `profile_proposal.consent_json`) and 0005 (`provider_connection.use_for_jobs`).

**Why:** Closes the details left open by ADR-010, ADR-033, ADR-035 and the privacy design (document 08) while keeping the default private: nothing leaves the machine without a visible, per-CV confirmation, and public job text never does.

**Consequence:** After pulling this change the dev images must be rebuilt and the database migrated. Existing setups that relied on `JOBS_RADAR_EXTRACTION_ENABLED` get one seeded local connection the first time the AI & privacy screen (or `GET /settings/ai`) is read; until then job analysis is off. OCR, PDF-to-image extraction and cloud analysis of jobs remain out of V1.

**Verified manually (2026-10-08):** with the local stack and Ollama (`qwen3:8b`), a synthetic CV produced 13 proposals in about 3 seconds, each with a verbatim quote, which were accepted into revision 1 with document provenance (headline, skills, languages, roles, education, certification, and Lisbon resolved to Europe/Lisbon); the profile was then removed with the audited deletion (13 evidence rows and the document record went with it) and the connection removed, leaving No AI. Remote providers were verified by tests with a spy provider only (no real cloud call was made).

### ADR-047 — Decisions taken while implementing T7 (company dossiers and market trends)

**Status:** approved by the owner (2026-10-09).

**Decision:**
1. **Company list.** `GET /companies` counts, per company, open offers and opportunities first seen in the last 7, 15 and 30 days, and the *relevant* subset (the latest evaluation of the opportunity's primary posting under the chosen intent has a fit at or above the threshold and is not `not_recommended`). The threshold is a request parameter with default **45**; it is not stored per intent yet. Default sort is the chosen window, then name; search covers names and aliases.
2. **Enrichment (builds on ADR-025).** Wikidata is searched by name; only entities that look like companies (a business class, or a description that says so) become candidates, so a library with the same name is never offered. An entity is accepted automatically **only** when the registered domain of its official website equals a domain already known for the company (homepage, careers address, or the address of one of its postings **outside job boards** such as Greenhouse, Lever or Ashby); every other entity is stored as a *pending* candidate (at most three) that the owner confirms or rejects. A rejected candidate is never proposed again. After acceptance, Wikipedia adds the description (shown with its CC BY-SA attribution), GLEIF adds the legal entity (only when exactly one record has the same name, ignoring legal-form suffixes) and GitHub adds technologies (only when the organisation's website has the same domain). Each fact keeps source, address, retrieval time and licence; a changed fact supersedes the old one, an unchanged one is not duplicated. All calls use the guarded client and are spaced out (1 s per dataset). New tables/columns (migrations 0006, 0007): `company_enrichment_candidate`, `company.enriched_at`, `integration_credential`.
3. **Refresh and token (owner's choices).** A company is refreshed on request or, once, when its dossier is opened and it was never looked up or is older than **30 days**; there is no background mass refresh. The **GitHub token is optional**, entered in AI & privacy, stored encrypted and write-only (ADR-033); without it enrichment runs anonymously.
4. **AI company summary.** Written on request from public facts and recent job titles only, by the **local** job-analysis model (never a remote provider, ADR-046), stored as a fact with origin `ai_inference` and displayed with that label; a newer summary supersedes the older.
5. **Trends.** Weeks start on Monday (UTC). *Relevant* uses the same rule as the company list. For each week and term the job stores open, new and closed counts, the relevant total and a hash of the source set (sources created by the end of the week). The first run backfills every week since the first opportunity; later runs recompute the last two weeks under the intent's **current** revision, so older weeks keep the revision they were computed with and the screen marks both **intent-revision** and **source-set** changes. Terms: skills by skill id, role families, sectors, work arrangement, seniority and engagement type by taxonomy key, followed through `replaced_by` so merged terms stay one line. The screen shows shares next to counts and offers 4 weeks, 12 weeks and 6 months (26 weeks) only once the history covers them. The worker runs the job when an enabled intent's aggregates are older than 24 hours; `POST /trends/recompute` does it on demand.
6. **API additions to document 07:** `GET /companies`, `GET /companies/{id}`, `POST /companies/{id}/enrich`, `POST /companies/{id}/summary`, `POST /companies/{id}/candidates/{id}/confirm|reject`, `PUT|DELETE /settings/integrations/{name}/credential` (GET /settings/ai also shows `integrations` status), `GET /trends`, `POST /trends/recompute`.

**Why:** Closes the details ADR-022 and ADR-025 left open while keeping the owner in control of identity (no automatic match without a domain proof) and keeping job and company text local.

**Consequence:** Companies without a known own domain (boards on Greenhouse only) will always show their best entity as a candidate to confirm. Trend history before the first run is a backfill from today's evaluations, not a historical record. Rebuild the dev images and migrate the database after pulling this change.

**Verified manually (2026-10-08):** with the real public datasets, enriching the `anthropic` board found Wikidata's entity (website anthropic.com) as a pending candidate because no own domain was known; after confirming, the dossier showed industry, headquarters, founding year and employees from Wikidata (CC0), the Wikipedia description (CC BY-SA) and GitHub technologies, each with source and licence; GLEIF returned no unique exact match and was skipped. Trends and the AI summary were verified by tests only (the dev database has no evaluated jobs and no local analysis model chosen).

### ADR-048 — Decisions taken while implementing T8 (operational hardening and release review)

**Status:** approved by the owner (2026-10-09).

**Decision:**
1. **Backups** (`jobs_radar.tools.backup`, `make backup`, `make restore-drill`, `make restore`) go to `backups/` inside the repository, which is git-ignored (owner's choice). Each backup is a private folder with the `pg_dump -Fc` dump, a manifest with its SHA-256 and the migration version, and the credential key as a **separate** private file. Restoring over a database needs explicit confirmation and a verified checksum; the drill restores into a scratch database and compares every table. The runbook tells the owner to keep the key apart from the dump and to copy `backups/` to another disk, because it sits on the same machine.
2. **CI is added** (owner's choice; reverses the deferral of ADR-019): a minimal GitHub Actions workflow runs `make install` and `make check` with read-only permissions, no secrets, and none of the network-only scans, the end-to-end tests or the smoke tests, which stay local (`make check-all`, `make test-e2e`, `make smoke`).
3. **Security gate.** `make config-check` (exposure, `.env` permissions, key validity, wildcard origins or hosts), `make security-audit` (pip-audit and pnpm audit, part of `check-all`), static tests that only the guarded client opens connections, that CV code never writes files and that Compose binds loopback by default, and a wider log-redaction list (source excerpts, extracted and raw text). Exposing the API or the database beyond loopback is a **warning**, not a failure, because LAN use is a legitimate choice (ADR-009).
4. **Opt-in smoke tests** (`make smoke`, `JOBS_RADAR_SMOKE=1`): a real Greenhouse board, Wikidata and a local model; a cloud provider only when `JOBS_RADAR_SMOKE_API_URL` and `JOBS_RADAR_SMOKE_API_KEY` are set. They use synthetic text, send no personal data and are skipped in the default run.
5. **Documentation.** An About & credits page (GeoNames, Wikidata, Wikipedia CC BY-SA, GLEIF, Greenhouse) and `docs/operations/` (configuration reference, operations guide, backup and restore runbook, sources and providers runbook, known limitations, release acceptance), with tests that every setting is documented and that the workflow and runbook commands exist.
6. **ODR-007 (licence and publication):** at the time of this decision the intention was personal use without publishing. This was superseded by the public release: the repository is licensed under Apache-2.0 (see the note at the end of this log).

**Why:** Meets the Increment 6 deliverables of document 09 without widening the attack surface: backups and keys stay local, CI has no credentials, and real-service tests never run by accident.

**Consequence:** `backups/` can hold the only copy of a key if the owner is careless; the runbook and `config-check` call it out. The owner's trial period and sign-off in `docs/operations/release-acceptance.md` are the remaining step before V1 is declared released.

**Verified (2026-10-09):** a clean clone passed `make install` and `make check`; the restore drill passed on the development database (40 tables) and on synthetic data in the tests; `make check-all` passed (including the dependency audit, with no known vulnerabilities); `make smoke` passed against a real Greenhouse board, Wikidata and a local model; `make config-check` on the owner's `.env` warned that the API and the database are bound to all interfaces.

### ADR-049 — Job boards as a second kind of source

**Status:** proposed and approved by the owner on 2026-10-09; the owner did not answer the four questions below, so the proposed defaults apply (country filter `PT` plus worldwide remote, boards added enabled after a preview, Remotive and Remote OK in the second wave, ITJobs.pt terms read once the key arrives). Research: `docs/research/R-00173-job-boards-as-sources.md`. Amends ADR-012 and ADR-015 (a source is no longer always one company board), extends ADR-023, ADR-033, ADR-042 and ADR-044; touches ADR-022 and ADR-047 (trends). Design of the screen: `docs/design/job-boards-ui.md`.

**Decision:**
1. **Two source categories.** *Company boards* (Greenhouse, later Lever, Ashby, SmartRecruiters, Recruitee, Workable): one source is one company, as today. *Job boards* (first wave: `arbeitnow`, `jobicy`, `himalayas`, `itjobs_pt`): one source is a whole board that publishes postings of many companies. The category is derived from `source_type` in code (`source_category()`); no new column. New `SourceType` values are added with a migration of the CHECK constraint. Second-wave candidates (Remotive, Remote OK, Working Nomads, HN "Who is hiring") need no new ADR, only an entry in the catalogue and an adapter.
2. **A code catalogue, not free URLs.** Job boards come from a fixed catalogue in `adapters/sources/catalogue.py` (type, display name, coverage note, official endpoint, requires-credential flag and label, politeness limits, attribution text, terms note and the date the terms were read, default filters). The owner adds a board by picking it from the catalogue; the stored `url` is the catalogue endpoint. No user-typed URL is accepted for this category, so SSRF exposure does not grow (ADR-035). A board is added once per owner (`external_identifier` is the catalogue key).
3. **Credential, only where the catalogue says so (ITJobs.pt first).** The Sources screen asks for the key when adding such a board, validates it against the real service before saving, and stores it Fernet-encrypted in the existing `source_configuration.credential_ciphertext` (ADR-033). It is write-only: the API returns only `credential_status` (`saved`, `none` or `not_needed`) and its date; the key can be replaced or removed afterwards (`PUT` and `DELETE /api/v1/sources/{source_configuration_id}/credential`). The adapter receives the decrypted key only for the call, sends it as the service requires, and it never appears in the stored `url`, logs, error messages, run results, raw payloads or exports. The log-redaction list gains the key parameter names. A refused key is error class `authentication` and never retried.
4. **Per-source filters applied before storage.** `config_json` (Pydantic-validated, `schema_version`) holds `categories` (default software/data/devops/security), `search_terms`, `max_age_days` (default 30) and `max_postings_per_run` (default 500). The countries are **not** a source setting (item 11). Postings that do not pass are **not stored**, which bounds the number of local-model extractions (ADR-044). Each run result records the filter version used and how many postings were dropped.
5. **A truncated run never closes postings.** When a run stops at `max_postings_per_run` or at a page limit, its outcome is `partial` and it does not count as a "successful run without the posting" for the closing rule of ADR-042.2. Changing the filters also does not close postings: postings left out by a new filter are closed only by the normal two-complete-runs rule. A filter change or enabling or disabling a board is a *source change* marker in the trends (ADR-047), because it shifts what the weekly shares measure (ADR-022).
6. **The company comes from the posting.** `SourcePosting` gets `company_name` (optional; required for job boards). For a job board `source_configuration.company_id` stays empty and the pipeline resolves the company of each posting by normalised name (`CompanyRepository.get_or_create`), once per name per run. A posting without a company name is dropped and counted.
7. **Duplicates against company boards (ADR-023).** No change to the rule or the thresholds: a board listing and the same company's board listing are linked when company, title, place, description and dates are alike, reversibly. New: when an opportunity has both, the **company-board listing is the primary posting** (it is source-authoritative), the board listing stays linked as another source.
8. **Politeness and terms are catalogue data.** Each entry declares a minimum interval between runs (for example Jobicy 60 minutes, Remotive 6 hours) which also applies to "Run now" (refused with `409 too_soon` and the time when it is allowed), a request rate, a response cap, and the paging style. The daily schedule remains the normal trigger. Attribution is kept per source and shown wherever a posting is shown: "Found on {board}" with the canonical link back, a "delayed 24 h" note where the board delays its data, and a credits entry on the About page. Boards whose terms forbid storing (We Work Remotely) or that need scraping (LinkedIn, Indeed, Glassdoor, Net-Empregos, Welcome to the Jungle, Landing.jobs, Wellfound) are **not** in the catalogue. Terms were read, not reviewed legally; ODR-007 stays open.
9. **Adapter contract.** `JobSourceAdapter.validate(identifier, credential)` and `SourceCheckpoint` carry the decrypted credential and the parsed filters; `BoardInfo` gets `matching_count` for the add-board preview. Paging (Arbeitnow `page`, Jobicy cursor, Himalayas offset) is inside the adapter and bounded by the filters and the rate limit. Where the board gives no ETag, a run fetches the filtered feed again; the unchanged-posting hash of ADR-042.3 keeps this cheap downstream.
10. **Tests and seed.** Tests use synthetic recorded responses written from each board's documented shape (never a live payload) with `respx` and the network block (ADR-015, ADR-035). The ITJobs.pt adapter is built from its documentation and sandbox, and is finished only after the owner has a key and confirms the response fields; until then its catalogue entry is hidden. No catalogue board is seeded and none is collected until the owner adds it from the screen. Opt-in smoke tests may cover Arbeitnow, Jobicy and Himalayas (`make smoke`).

11. **Location comes from the profile and the intents, never from the source** (owner's instruction, 2026-10-09). The countries a job board is asked for (`country=PT`, `geo=europe` ...) are derived at run time and at preview time: the **country of the base location** the owner wrote in the Career Profile (for hybrid or on-site work) plus the **countries of the eligible regions** of each *enabled* Search Intent (for remote work, groups such as EU or UK expanded to countries, `WORLD` meaning any country). An arrangement the intent rejects contributes nothing; worldwide postings are wanted only if some enabled intent accepts remote work. `GET /api/v1/source-scope` shows the result read-only. With no enabled intent the scope is empty and a job board fails with class `configuration` ("Set your base location and remote regions in Profile & intent first.") **before any request**. Only country codes or region slugs reach a board, never the place text or the profile.

**Why:** One company board (Anthropic) does not fit the owner's profile (Portugal, remote); company boards stay the best-quality source, but boards are the only practical way to discover companies and roles outside a hand-made watchlist (R-00173). A code catalogue keeps terms, limits and attribution reviewable and avoids a generic "paste any feed URL" feature, which would need scraping-grade defences.

**Consequence:** Collection, the pipeline and the Sources screen change; the matching module, the inbox rules and the extraction prompt do not. Volume is controlled by filters, not by trimming the extraction queue. If a board changes its terms, its catalogue entry is edited (or removed) in code. Currency stays "same currency only" (several boards publish salary in USD).

**Questions for the owner (answers change the first implementation):**
- *Default filters.* Answered by item 11: countries come from the profile and the intents. (Himalayas lists eligible countries, so its country filter is exact; Arbeitnow and Jobicy rely on the board's own region and the model's location judgement.)
- *Added enabled or disabled.* Proposal: a board is added **enabled**, after a preview of how many postings pass the filters ("212 of 1,398 match"), and nothing runs until "Run now" or the schedule.
- *Remotive* (24 h delay, 17 postings in the free feed) and *Remote OK* are second wave; confirm that is acceptable.
- *Terms read by the owner* for ITJobs.pt once the key arrives (the pages read did not state them).

**Verified (2026-10-09):** the running stack was restarted (migrations 0009 and 0010 applied, `/readyz` ready); the Sources screen showed the Company boards and Job boards sections with the location taken from the real profile (the EU countries and remote work from anywhere); a real preview of Himalayas answered in 22 seconds with at least 100 matches; `make smoke` read real postings from Arbeitnow, Jobicy and Himalayas. Not yet verified: a key-protected board (ITJobs.pt), and adding a board to the development database.

### ADR-050 — Lever, Ashby and SmartRecruiters company boards (T10)

**Status:** approved by the owner on 2026-10-09; implements the follow-up announced in ADR-015 and extends ADR-042. Research: R-00169 and live checks of 2026-10-09.

**Decision:**
1. **Three more company-board types**, one company per source, added by identifier like Greenhouse: `lever` (`api.lever.co/v0/postings/{company}?mode=json`), `ashby` (`api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true`) and `smartrecruiters` (`api.smartrecruiters.com/v1/companies/{company}/postings`). New `SourceType` value `smartrecruiters` (migration 0011); all four are `company_board` and employer ATS for `dedup-v1` (their listing is preferred as primary).
2. **Lever and Ashby** return every posting in one answer and support `If-None-Match` (ETag, HTTP 304), so they behave like Greenhouse. Ashby postings with `isListed` false are ignored; the compensation summary Ashby shows is appended to the text as "Compensation: ...". Neither publishes a company name, so the name is guessed from the identifier and the owner may type the real one (`display_name` in `POST /api/v1/sources`).
3. **SmartRecruiters** lists postings without text, so each posting needs one detail request. To keep that bounded: the detail is read only for postings that look technical (SmartRecruiters' own `function` is `information_technology` or `engineering`, or a technology word is in the title, using the job board rules) and at most 200 per run. A run that finds more is `partial` and never closes postings (ADR-049.5); listing stops once more are known than can be read. The default pace is 30 requests a minute. SmartRecruiters answers 200 with no postings for an unknown company, so a company without postings is refused as not found.
4. **Identifiers** are validated before any request (letters, digits, dot, hyphen, underscore, up to 100) because they become part of a URL. All requests go through the guarded client, the polite getter (spacing, at most three attempts, `Retry-After`) and are never made by tests (synthetic fixtures, `respx`); `make smoke` reads one real board of each.
5. **No new UI category**: the "Add a board" card of the Sources screen gets a board type selector; the identifier label and hint follow the type, and the company name field appears only for Lever and Ashby.

**Why:** Many European and Lisbon companies publish on these ATS; direct company boards give cleaner data than job boards (R-00173) and answer the owner's wish for more coverage near Lisbon.

**Consequence:** The owner must find each company's identifier (it is the last part of its careers address). A company with thousands of SmartRecruiters postings is read in slices of 200 technical postings per run. Lever has no public company name and Ashby neither, so the guessed name may need the owner's correction at add time (it cannot be edited afterwards in this version).

### ADR-051 — Opt-in filters for company boards (T11)

**Status:** approved by the owner on 2026-10-09; extends ADR-049.4 and ADR-050.

**Decision:**
1. **Off by default.** A company board keeps every posting, as before. The owner can opt in per board ("Keep only postings that match my areas and location"); the filters are the same `JobBoardFilters` as for job boards (technology areas, search terms, posted within N days, most postings per run) stored in `config_json`. `PUT /api/v1/sources/{id}` takes `filters` to opt in or change them and `clear_filters` to opt out (not allowed for job boards, whose filters always exist).
2. **Applied after the fetch, before storage**, in the collection service, so every adapter benefits and none changes. A `304` carries no postings and is not filtered. Postings left out are counted in `dropped_count`; a run stopped at the per-run limit is `partial` and never closes postings (ADR-049.5). Postings stored before the filters were turned on are closed only by the normal two-complete-runs rule.
3. **Location is read from the places the company publishes**, because a company board gives no structured eligibility. Per place: a text with "remote", "remoto", "anywhere", "worldwide" ... is remote work open to the regions it names (`Remote - EU`, `Remote, Europe`, `Remote - Portugal`; no region named means unknown); any other text is a workplace and must be inside the radius of the owner's places (the same Lisbon radius as job boards) when its city can be read offline (GeoNames). A posting with several places passes if any place does; a place that cannot be read, or a posting without places, is kept for the later judgement. The countries and radius come from the profile and the enabled intents (ADR-049.11); with no known scope the location is not filtered.
3c. **SmartRecruiters with filters on** lists only the owner's countries (`country=pt` for each country of the location scope; every country when remote work from anywhere is accepted), so a large company's postings elsewhere are never read and the 200-detail limit is spent on postings that can pass.
3b. **Corrections found on real data (2026-10-09).** A place that is a bare country (`Spain`, the usual form for distributed teams such as Elastic) is a country where the person may live, not an unreadable place; markers such as `Hybrid` or `In-Office` are not places. A filtered board is always fetched without its ETag and the ETag is forgotten when the filters change: a `304` refreshes every open posting, so postings that the filters now reject would never go unseen and never close.
4. **Areas** use the rules of ADR-049 (title and departments), including the noise list for data-labelling gigs.
5. **UI:** the company boards table gets a "Filters" row per board (opt-in checkbox, the same fields as a job board, save with the version the owner saw).

**Why:** Large employers publish hundreds of postings (Elastic, Datadog, Cloudflare: about 430 each) of which a handful are in the owner's reach; each stored posting costs a local-model extraction of about ten seconds.

**Consequence:** A technology-area match on the title is loose on purpose; the evaluation still decides fit. Free-text places are noisy ("Hybrid - Lisbon / Madrid"), so unreadable places are kept rather than guessed.

### ADR-052 — Country names in remote regions

**Status:** proposed on 2026-10-09 and **approved by the owner the same day**; implemented. The policy version is now `matching-v1.1`; evaluations made under `matching-v1` stay as they are.

**Finding:** The extraction model often writes the eligible regions of a remote job as country *names* (`["Austria"]`). `regions_intersect` only knows ISO codes and the groups EU, EEA, EUROPE, UK and WORLD, so a name is "not recognised" and the evaluation says "Remote, but the stated regions are not recognised (treated as a risk)": a job open only to Austria still scores as a match (63 of 100, `recommended`) for an owner whose remote region is `PT`, instead of failing hard gate G2. Observed on postings of the Himalayas board with the intent revision whose remote region is `PT`.

**Proposal:** map country names to ISO codes when the stored extraction becomes `JobAttributes` (`services/evaluation_inputs.py`, offline GeoNames lookup already used by the adapters), keep groups, codes and other text as written, and **raise the policy version** (`matching-v1` to `matching-v1.1`) so that existing evaluations stay as they are and a rescore (no model call) creates new ones. Unit tests: names become codes, `EMEA` and `Worldwide` stay as written.

**Why not now:** the same stored extraction would give a different score under the same policy version, which breaks the rule that an evaluation is a deterministic function of its stored inputs and policy version.

**Also approved with it:** a fifth technology area `telecom` for the pre-filters (words such as BSS, OSS, billing, telecom, charging, mediation, revenue assurance), because the owner's preferred role family `telecom_billing_bss_oss` matched none of the four areas.

**Consequence:** `POST /api/v1/intents/{id}/rescore` re-evaluates every open job once; remote jobs restricted to other countries become `not_recommended`.

### ADR-053 — Followed companies and a tidier Companies screen

**Status:** designed with the owner on 2026-10-10 (mock-up `docs/design/companies-mock.html`) and approved to proceed (recency limit configurable, 30 days by default); implementation follows in steps.

**Finding:** every company seen in a posting is listed, so the Companies screen grows without bound, companies the owner wants to watch get lost, and the offers of a company are an unranked list with no fit or triage state. The "Is this the company?" candidates could not be told apart (the Wikidata link is already shipped, with no decision needed).

**Decision:**
1. **Follow** is personal state, not a company fact: a table `company_follow` (`owner_id`, `company_id`, unique together, `created_at`; no soft delete, unfollowing deletes the row). Followed companies are pinned on top of the list even with no open offers.
2. **Recency limit:** offers older than a configurable number of days (default **30**, a GUI setting stored in the database like the schedule) are left out of the company counts, the best fit, the sort order and the default offer list. They stay reachable with an explicit "Older" filter. Closed postings follow the same rule.
3. **Ignored offers do not count** towards the open and recommended counts, the best fit or the sort order; they stay visible, dimmed, inside the company.
4. **List:** server-side search, filters (followed, with open offers (default on), recommended, needs identification), sort by best fit among counted offers, and pages of 50. The offers of a company reuse the Inbox row (fit, band, triage state, shortlist).
5. Nothing changes in matching, scoring or collection; the follow state never affects an evaluation.

**Consequences:** a migration for `company_follow` and the setting; new fields on `CompanySummary` (`is_followed`, `best_fit_score`, `recommended_offers`, `pending_candidates`) and follow/unfollow endpoints with idempotent `PUT`/`DELETE`; `make api-client` and `make docs-schema`.

### ADR-054 — Company website discovery and deep company dossier

**Status:** approved by the owner on 2026-10-10 (manual runs only, no schedule). The owner chose: public company pages read by the **local** model only, no remote LLM, sources limited to the company's own domain plus the open datasets already used. 

**Finding:** 3 of 754 companies have a known website. ADR-025/047 accept a Wikidata entity automatically only on an equal registered domain, so the rule almost never fires; most companies stay "Nothing is known beyond the job board yet" and every Wikidata hit is left pending. The one-company `POST /companies/{id}/enrich` already exists but depends on that same missing domain. The summary (ADR-047) only paraphrases a few facts and job titles.

**Decision:**
1. **Website first.** A company's website is the key to everything else. It comes from a non-job-board posting URL already stored (the existing automatic match), from confirming a Wikidata candidate (which already records its website), or from the owner typing it (`PUT /companies/{id}/website`, reduced to `https://host/`, job-board addresses refused). Only that website feeds `_known_domains`, so the existing automatic Wikidata/Wikipedia/GLEIF/GitHub acceptance then works unchanged. No separate "website candidate" fact is stored (implementation simplification).
2. **Per-company deep analysis** (button on the company, plus an optional "analyse followed companies" batch). It reads at most 8 public pages **of the confirmed registered domain only** (home, about, careers, engineering blog, remote-work/handbook pages found from the home page links), through the existing `GuardedHttpClient` + `UrlGuard`, honouring `robots.txt`, with a spaced-out interval, size and time bounds, and no redirect off the domain. Text is cleaned with the existing HTML helpers.
3. **Local model only** (ADR-046: job and company analysis stays local; no fallback to cloud). The model returns a schema-validated dossier: product and business model, size and stage, technology stack, engineering culture, remote/hybrid policy and Portugal presence, risks and open questions. **Every statement carries a verbatim quote from a page and its URL**; statements without a verifiable quote are dropped (same rule as job extraction, ADR-044). Stored as `CompanyFact` rows with `origin=ai_inference`, source URL, retrieval time and the model, labelled "AI inference" in the UI; a new run supersedes the old one, history is kept.
4. **No new data leaves the machine**: page text goes only to the local model; nothing is sent to a remote service; no third-party scraping (Glassdoor, LinkedIn, Crunchbase are out).
5. Nothing changes in matching, scoring, collection or the follow state.

**Consequences:** no migration (reuses `company_fact`, key `ai_dossier`); new adapter `adapters/enrichment/website.py`, service `company_analysis.py`; endpoints `PUT /companies/{id}/website` and `POST /companies/{id}/analyse`; Companies screen shows website state, the analyse button and the cited dossier; `make api-client` and `make docs-schema`.

**Scheduling:** manual only; no worker schedule in V1 (owner decision).

### ADR-055 — Careers-site sources for telecom and BSS employers (Eightfold, Workday, Teamtailor, generic page)

**Status:** **approved by the owner on 2026-10-10**. Step 1 below is implemented for Eightfold (migration 0014); Workday, Teamtailor, the URL detector (2) and the generic careers-page source (3) follow, each when the owner asks. It changes collection sources (ADR-012, ADR-015, ADR-050). Research: live checks of 2026-10-10 (below).

**Finding:** the target employers are telecom operators and BSS vendors, in Portugal and in remote Europe. The employers that matter (operators and BSS vendors) mostly do **not** use Greenhouse, Lever, Ashby or SmartRecruiters. Only Netcracker does (added as source 44 on 2026-10-10: 19 postings, about half of them not technical). Checked on the companies' careers pages:

| Employer | System | Public JSON |
|---|---|---|
| Amdocs, Vodafone, Ericsson | Eightfold (`jobs.<company>.com`) | `/api/pcsx/search?domain=<domain>&query=&start=` answered with postings for Amdocs and Vodafone; Ericsson not tested |
| CSG, Mavenir, Infobip | Workday | `POST /wday/cxs/<tenant>/<site>/jobs` answered for CSG |
| Celfocus | Teamtailor | not tested |
| Synchronoss | iCIMS | not tested |
| Oracle | Oracle Cloud Recruiting | not tested |
| Digi PT, NOS, MEO/Altice | own pages or an unidentified portal | none known |

Zon is now NOS (merged with Optimus in 2013) and Nowo belongs to Digi (2024), so neither is a separate target.

**Decision (proposed):**
1. **Deterministic adapters per careers system**, same `JobSourceAdapter` contract, one company per source, added by an identifier and validated before saving (ADR-050 rules for identifiers, guarded client, polite getter, `respx` fixtures, `make smoke` for one real board each). Order: `eightfold` (Amdocs, Vodafone, Ericsson), then `workday` (CSG, Mavenir, Infobip), then `teamtailor` (Celfocus). iCIMS and Oracle Cloud wait until the owner needs them. New `SourceType` values need one migration each. These are public, unauthenticated JSON endpoints that the employers' own careers pages call; if a system's terms or `robots.txt` forbid it, that employer is not added.
2. **Detection from a URL.** The owner pastes a careers URL; a fixed detector (no AI) looks for the known system markers in the page and proposes the source type and identifier, which the owner confirms. This is what was done by hand in the research.
3. **Generic "careers page" source, with the local model, for employers on no known system** (expected: Digi PT, NOS, MEO). The local model (ADR-046, never a remote one) reads the page text and **proposes a configuration** (listing URL, how a posting is delimited, the field for title, location and link). The owner reviews and approves it; from then on a fixed, schema-validated reader executes the approved configuration with **no AI in the normal runs**. The model never generates or executes code. If the page stops matching the configuration the source fails with a clear reason (`schema_changed`) and the owner may ask the model for a new proposal; the previous configuration is kept in history. Pages are read only on the employer's own domain, honouring `robots.txt`, with the `UrlGuard`, size and time bounds, as in ADR-054. A page rendered only by JavaScript is out of scope and reported as such (no headless browser in this ADR).
4. **Company before the first offer.** A source creates its company when it is added (already true for company boards), so the employer appears on the Companies screen and can be followed (ADR-053) before any offer exists. Companies without any source stay impossible to create by hand; that is not changed here.
5. **Filters.** The opt-in area and reach filter of ADR-051 applies to the new company-board kinds as well; large vendors such as Amdocs and Ericsson publish thousands of postings worldwide, so a run limit and a `partial` outcome (ADR-049.5) apply.
6. Nothing changes in matching, scoring, privacy or the inbox. Fixtures are synthetic; tests make no network request.

**Why:** the owner wants to be alerted when operators and BSS vendors publish roles. A few fixed adapters cover most of the named employers cheaply and reliably; the model is used once, to configure, so the daily run stays deterministic, auditable and free of AI cost.

**Consequences:** new adapters and detector in `adapters/sources/`; a "from a careers URL" flow in the Add a board card; a review step for generated page configurations; `SourceType` migrations; `make api-client` and `make docs-schema`. Risk: the Eightfold and Workday endpoints are public but undocumented, so they may change; each adapter fails visibly (never silently) and one failure never blocks other sources.

**Implementation note (ADR-070 backlog, 2026-10-14):** a careers-page source (`page_jsonld`, `page_config`) that has never completed a run (`success`) reads its whole backlog: its page and detail limits and the per-run limit on kept postings are ignored (`SourceCheckpoint.backlog`). Later runs keep the limits. The dossier's board result carries `last_dropped_count` and `filters_enabled`, and the Collection card offers to turn the filters off and queue a run.

**Implementation note (Eightfold, 2026-10-10):** the identifier is the careers host (`jobs.amdocs.com`); the company domain is the host without its first label. Listing is ten postings a page, newest first (`sort_by=timestamp`), at most 200 pages; with the filters on, one listing per country of the owner's scope (`location=<country name>`). Details are read for every listed posting without filters, and only for titles that fit a chosen area with filters; at most 200 per run, beyond which the run is `partial`. Default pace 30 requests a minute. The remote postings of the whole site are listed too (`location=Remote`), because Eightfold marks work from home as `remote_local`, meaning remote inside the posting's own country: such a posting is written as `Remote - <country>` so the pre-filter keeps it only when that country is the owner's. A site whose search answers without `data` is refused as not an Eightfold careers site. The age filter of ADR-051 (30 days by default) compares with the first publication date, so a long-open posting is dropped by it; for company boards the owner may raise it up to 365 days.

**Open questions for the owner:** (a) ~~approve the order of adapters above~~ approved; (b) confirm that a JavaScript-only page is out of scope for now; (c) confirm that big vendors are added with the ADR-051 filter on by default.

### ADR-056 — The source's own location limits the remote regions the model reports

**Status:** **approved by the owner on 2026-10-10** after an audit of the inbox. Items 1 and 4 are implemented (`matching-v1.2`); item 3 (prompt rule 6) is **not** implemented yet, see the implementation note. It changes scoring semantics (what feeds gate G2 and the work-arrangement dimension).

**Finding (audit of 2026-10-10):** of the 908 recommended items among the 1,200 best-fitting in the inbox, **28 (3%)** have a source location outside Europe while the model reports remote regions that include Portugal (`WORLD`, `EU`, ...). Examples: `India (Remote)`, `Japan (Remote)`, `Israel (Remote)`, `United States (Remote)` (Grafana Labs), `Remote US` (Mozilla, where the model answered `EU` from "some regular overlap with European business hours is expected"), and hub-office lists such as `New York, San Francisco, Toronto` (Cohere) reported as `WORLD`. Causes: (1) the model infers an eligibility the posting does not state, and the verbatim quote it gives is a sentence that mentions a region without granting eligibility; (2) the source's own structured location is never compared with `remote_regions` (the existing contradiction check only compares extracted *locations* with the source's). Because the owner's priority is fully remote work from Portugal, such false positives sit at the top of the inbox.

**Decision (proposed):**
1. **A deterministic guard in `services/evaluation_inputs.py`** (not in the model, not in the pure engine): when every source location of a posting is a *remote place bound to a country or region* (`India (Remote)`, `Remote - US`, `Remote US`), the job's remote regions are the intersection of the model's regions with that place. An empty intersection means the job is open from no region of the owner's, so gate G2 applies, with the source location shown as evidence.
2. **Hub-office lists** (`New York, San Francisco, Toronto`, no word "remote") do not restrict anything by themselves: the model's regions stand, but the evaluation notes that the source lists only offices. No gate is added.
3. **Prompt rule 6** states that `remote_regions` is filled only when the posting names the regions remote work is open to; a mention of customers, partners or business hours in a region is not eligibility. This needs a new prompt version, so extractions are made again (append-only, new rows).
4. The change applies at evaluation time: a **rescore creates new evaluations** with a new policy version (`matching-v1.2`) and keeps the old ones; the prompt change creates new extractions only for new or changed postings unless the owner asks for a re-extraction of the recommended ones.

**Why:** the score must be a deterministic function of stored facts, and the source's own structured location is a stronger fact than a small model's reading of free text. The guard only ever narrows eligibility, so it cannot create a false positive.

**Implementation note (2026-10-10):** `services/remote_places.py` reads the board's own places; `evaluation_inputs.job_attributes` narrows the model's regions with them and says so in the quote. Only the model's *known* regions are narrowed: unknown regions stay unknown (the rule never turns an unknown into a match). A bare `Remote` that an adapter adds next to a bound place is ignored; a named office, a region that is not understood (for example `AMER`) or a place open to everyone means the source limits nothing. `Netherlands` was added to the country aliases (GeoNames calls it `The Netherlands`). Item 2's evaluation note for hub-office lists is not implemented (no behavioural effect). **Item 3 is postponed:** a new prompt version makes every open posting (about 5,300) lack an extraction of the current version, so the worker would re-extract all of them with the local model (hours). It needs the owner's decision on when and for which postings.

**Consequences:** about 3% of the currently recommended items would move to `not_recommended`; a test set built from the 28 audited cases; a new policy version and a rescore; the inbox UI shows the source location as evidence. Open question: should an item whose source location is `Remote <country>` with the country inside the owner's regions (for example `Remote - Portugal`) be shown as a strong match?

### ADR-057 — Career directions: free-text goals judged by the local model

**Status:** **approved by the owner on 2026-10-10** and implemented (`matching-v1.3`, migration 0015).

**Finding:** the stance model (ADR-026) and the skills cannot say what a person is actually after, for example "I am a data engineer who wants roles in the energy sector; I am also moving into machine learning, backed by my own open-source work". Two such goals, written in plain language, should each be able to make a job a very good match.

**Decision (proposed):**
1. **Directions in the Career Profile.** `ProfileFacts` gets `directions`: a list of at most 5 items, each `{label (up to 60 characters), text (up to 1,000 characters, English), enabled}`. They are edited by hand in the Profile screen with a "+" button (add, edit, disable, remove). Saving creates a normal profile revision (ADR-043: no change, no revision). Imports from a CV never create or change directions.
2. **One judgement per job and per direction.** For each new job and each enabled direction the local model returns `level` (`strong`, `partial`, `weak`, `none`, `unknown`), a verbatim `job_quote` (up to 200 characters, checked against the posting as in ADR-044) and a verbatim `direction_quote` from the direction text. A level without a valid job quote becomes `unknown`. The judgement is stored in a new append-only table `direction_judgement` with the job snapshot, the SHA-256 of the direction text, provider, model and prompt version (`direction-v1`). It is keyed by that hash, so editing one direction only judges that one again, and editing skills or experience invalidates nothing.
3. **The best direction counts, decided by code.** A new dimension **Career direction** takes the highest known level among the enabled directions (`strong` 1.0, `partial` 0.5, `weak` 0.2, `none` 0), and the result names the direction that won ("fits: Billing SME in telecom") with both quotes. Choosing the maximum is deterministic code, never the model's task. If every judgement is `unknown`, the dimension contributes 0 (ADR-021). The final score stays a deterministic function of stored judgements.
4. **Weight.** `Weights.career_direction` is optional and defaults to **0** (excluded), like Benefits and Qualifications, so every existing intent is unchanged and a user without directions sees no difference. The owner sets it per intent; the owner's intent #4 is proposed at 15, taken from Role & responsibilities (25 to 10), as a new intent revision made by the owner after the sample test. The dimension adds at most its weight to the score: a very good fit overall also needs the other dimensions to agree.
5. **The past is not scored again.** A job without any judgement is **not assessed**: the dimension is left out of that evaluation and the other weights are renormalised (as for weight 0), instead of counting as 0, so old and new jobs stay comparable. Judgements are made by the worker only for jobs first seen after the first enabled direction was saved (a cut-off stored with the setting). Two explicit actions exist: **assess this job** (one posting on demand) and **test sample** (see 6). There is no bulk re-evaluation.
6. **Test sample.** Before the weight is raised, about 30 existing jobs are judged, chosen by the assistant: telecom/BSS roles, software and AI roles, and contrast cases including the false positives of ADR-056. A report lists, for each job, the old fit, the new fit, the winning direction and the quotes, for the owner to review. The sample is run with the model chosen in 7. Their new evaluations are appended (the old ones stay).
7. **Model.** The judgement runs on the local jobs connection (ADR-046: job analysis is local only, no remote fallback, direction texts never leave the machine). The owner may select a different local model for this step only; the sample decides whether `qwen3:8b` is enough or a larger local model (`qwen3.6:27b`, `gemma4:26b`) is used for judgements while extraction stays on the small one.
8. **Policy** `matching-v1.3`: same rules plus the new dimension. The engine receives the judged levels as input and stays a pure function.

**Why:** a list of independent short texts keeps the feature general (any number of goals, no assumption about the owner's career), makes "the best fit wins" a rule in code, and keeps the cost bounded: one short call per job per enabled direction, for new jobs only.

**Consequences:** a migration (`direction_judgement`, setting for the cut-off, `career_direction` dimension key and column checks); prompt and schema `direction-v1`; worker step after extraction; Profile screen section with a "+" button; inbox and detail show the winning direction or "not assessed"; the weights editor gets the new dimension (greyed at 0); doc 13 (dimensions, level factors), `make api-client` and `make docs-schema`. With N enabled directions a new job costs N short model calls; the limit of 5 bounds it. Risk: a small model may judge poorly, which the sample is meant to show before any weight is raised.

**Implementation note (2026-10-10):** (a) the factors, the cut-off rule and the limits were approved with the ADR. The cut-off is derived, not stored: it is the creation time of the first profile revision that has an enabled direction. (b) The test sample is a command-line tool (`python -m jobs_radar.tools.direction_sample`), not an endpoint, because judging 30 jobs takes minutes; it also prints a what-if score with other weights, stored nowhere. (c) `Weights.career_direction` defaults to 0 in the schema; the proposed 15 (taking 15 from Role & responsibilities, 25 to 10) is for the owner to set on the intent after the sample. (d) A judgement whose answer stays invalid after one repair is stored as `unknown` so the job is not asked again and again; a timeout is retried later; a model that is down stores nothing. (e) A job is scored again, as a new evaluation with a new `direction_basis`, whenever a judgement is added; the inbox shows the newest. (f) Raising `POLICY_VERSION` makes the worker score every open job again under `matching-v1.3` (a deterministic step with no model call). (g) The model for directions is a setting of the local jobs connection (`config_json.direction_model`, edited in AI & privacy); empty means the job model, and the worker, the on-demand assessment and the sample tool all use it. (h) On the 30-job sample (10 telecom/BSS, 10 software/AI, 10 contrast) `qwen3:8b` rated unrelated jobs strong and left two AI-engineer postings `unknown`; `qwen3.6:27b` rated all contrast jobs `none`, the AI-engineer postings `strong` and OSS-only telecom roles at most `partial`, with no `unknown`, at about 2 seconds per judgement.

### ADR-058 — Jobs the owner cannot apply for are set aside by default

**Status:** **approved by the owner on 2026-10-11**. It changes scoring semantics (two new cases of gate G2) and what the inbox shows by default.

**Finding (audit of 2026-10-11, 4,444 open evaluated jobs, intent revision 12):** 2,342 (53%) are already blocked by a hard gate and 135 of them still score 45 or more, yet they all appear in "To review". Of the rest, 1,006 have a confirmed location, 615 are remote with no stated regions and 481 have an unknown location or arrangement. Reading the source's own places for the 615 shows 212 that are clearly not open to Portugal (`Remote - USA`, `US - Remote Zone 1`, `Remote Canada`, `Home based - Americas`, `North America`); among the 481, 210 list only far offices (`San Francisco, CA | New York City, NY`) and say nothing about remote work. ADR-056 narrows the regions only when the model reported some; when it reported none the engine gives 80% of the location points "as a risk", which lets these jobs through. Region groups such as `EMEA`, `AMER`, `APAC`, `LATAM`, `Americas` and `North America` are not understood.

**Decision:**
1. **Close the leak.** When the work is remote, the model reported no regions and the source's places are all remote places bound to countries or regions (ADR-056 reading), those countries become the job's remote regions, with a note in the evidence. The existing gate G2 then applies. Places that limit nothing (an office, an unknown region, `Worldwide`) keep today's behaviour.
2. **Far offices without a remote statement.** When the work arrangement is not stated, every job location is placed on the map and all are outside the owner's distance, the job is blocked by gate G2 ("every location is far away and the posting does not say it can be done remotely"). An unplaced location or a stated arrangement is never touched by this rule.
3. **More region groups** in `domain/regions.py`: `EMEA`, `AMERICAS`/`AMER`, `NORTH AMERICA`, `LATAM`, `APAC`, with aliases (`United States` names are already countries). They are used both for the model's regions and for the source's places; the filler `Zone N` is ignored when reading places.
4. **Set aside, not ignored.** The inbox list gets a filter `set_aside` (`true`: only jobs whose latest evaluation for the chosen intent is `not_recommended`; `false`: without them; a job without an evaluation is never set aside). "To review" uses `false`, a new tab **Set aside** uses `true` over unread jobs, and each row there shows the first gate reason. No inbox state changes, no events are written and nothing is stored per job: the partition follows the stored evaluations, so it changes by itself when the profile, the intent or the policy changes (a rescore) and the owner can open any of these jobs. Companies, search and the other tabs still list them.
5. **No new model call.** All facts come from the stored extraction and the source's places; the model only extracted them before.
6. **Policy** `matching-v1.5`: v1.3 plus 1 and 2. Evaluations of earlier versions stay; a rescore creates new ones.
7. **Not done here:** turning on the ADR-051 filters of the company boards that have none (they would stop storing ineligible jobs, which the owner does not want because they should stay visible under the companies).

**Why:** the owner cannot read thousands of items per day, and the eligibility facts are already stored. Making the rule deterministic keeps the score a function of stored judgements (ADR-021), costs no GPU and can be audited from the evidence.

**Implementation note (2026-10-11):** the policy is `matching-v1.5`: a first run labelled `matching-v1.4` read `US - Remote Zone 1 (Job Requisitions Only)` wrongly, and evaluations of one policy version are never repeated, so the corrected rules got the next label (`matching-v1.4` evaluations exist only in the development database). The rescore now also covers jobs scored under an earlier policy; before, only the worker's slow "new job" path (with model calls) reached them.

**Consequences:** `matching-v1.5` and a rescore; the API list takes `set_aside` and the counts hold the set-aside number; a new tab in the inbox; doc 13 and CLAUDE.md updated. Expected effect on the audited data: about 62% of the unread jobs move out of "To review".

### ADR-059 — Job briefing: an AI summary, the main technologies and the key facts above the description

**Status:** **approved by the owner on 2026-10-11** (summary in English; a second prompt is acceptable). It adds a model call per job and a table, but changes no scoring semantics.

**Finding:** the detail panel shows the score and its evidence, but not what the job *is*, so the owner opens "Open original" for almost every item to decide whether it is worth reading.

**Decision:**
1. **Summary.** A second prompt, `summary-v1`, separate from extraction, writes one or two short paragraphs in English (whatever the language of the posting): who is hiring, the role, seniority and years asked, main technologies, work arrangement, location, contract and pay when stated; then what the person would do and anything notable. It uses only what the posting states and says when pay or work arrangement is not stated. The model answers `{"summary": "..."}`; the text is trimmed and bounded (80 to 1,500 characters), one repair is attempted, and an answer that stays unusable is stored as a `failed` row so the worker does not ask again. Free text cannot be quote-checked like extractions, so the screen labels it "AI summary" and keeps the full description one click below.
2. **Storage.** New append-only table `job_summary` (job snapshot, provider, model, prompt version, status, text, error class, latency). One successful summary per snapshot, provider, model and prompt version (partial unique index); a new snapshot or a new prompt version gets a new summary, old ones stay. Summaries never feed the score.
3. **Model.** The local jobs connection (ADR-046): job text never leaves the machine and there is no remote fallback. Summaries use the larger local model the owner set for directions (`config_json.direction_model`, ADR-057 g), and the job model when none is set. Reason, from a three-job trial on 2026-10-11: `qwen3:8b` wrote plausible but invented details (a "hybrid" arrangement for a remote job, a "competitive salary" the posting never states), `qwen3.6:27b` stayed faithful at 3 to 6 seconds per job.
4. **Who gets one.** The worker writes summaries only for jobs first seen on or after `SUMMARIES_FROM` (2026-10-11, the release of this feature), after their extraction. Jobs analysed before are not summarised in bulk; the 30 best-ranked open jobs (by their latest fit for the first enabled intent) are summarised once with `python -m jobs_radar.tools.summary_sample` to check the feature, and any other job on demand (`POST /api/v1/jobs/{job_posting_id}/summary`, button "Generate summary"). Jobs without a summary show "The summary has not been generated yet."
5. **Technologies and key facts.** No model call: the detail endpoint returns the skills of the latest successful extraction (required first, then preferred), plus seniority, years asked, work arrangement and stated pay. The panel shows the technologies as chips (required emphasised, text label as well as style, first 8 and a "+N" disclosure) and the facts as one line, above the description.
6. **API.** `GET /api/v1/inbox/{id}` gains `brief` (`summary`, `summary_model`, `technologies`, `facts`); the list is unchanged.

**Why:** a short faithful briefing and the stack at a glance answer "is this worth opening?" without reading the posting; a separate prompt keeps the extraction JSON small (a small model degrades when asked for prose and a large schema at once); append-only storage keeps model and prompt provenance like every other AI output.

**Consequences:** migration 0016; one more model call per new job (about 2 to 5 seconds on the local server); the worker step runs after extraction and before scoring and ends quietly when the model is down; `make api-client`, `make docs-schema`. Open: highlighting the technologies that are in the owner's profile, and a bulk "summarise all open jobs" action, are not part of this decision.

### ADR-060 — Jobs outside the owner's fields: finance-type role families and a low-fit floor for "Set aside"

**Status:** proposed on 2026-10-11 and **approved by the owner the same day**, with these answers: the six proposed families; re-extract the open jobs; the floor defaults to 20 and is configurable; it is one setting (not per intent). Implemented as T12. Extends ADR-058; touches ADR-026 (stances), ADR-041 (taxonomy) and ADR-044.

**Finding (audit of the development database, 2026-10-11):** the inbox "To review" tab shows jobs such as "Finance & Strategy, Deal Strategy" (fit 4) and "Finance & Strategy GTM, EMEA" (fit 0), which have nothing to do with the owner's search. 23 `matching-v1.5` evaluations with "Finance" in the title are `recommended`. Cause, from the stored data:
- The taxonomy v1 has no family for finance, accounting, legal, HR, marketing or similar non-technical work (`other` is the only fallback), so the model returns `role_families: []`. The role dimension is then `unknown` and gate G1 (every identified family rejected) cannot fire (`domain/matching/engine.py:116-125`).
- Those postings state a hybrid arrangement but no placed location, so gate G2 cannot fire either (`engine.py:211-227`).
- Everything else is `unknown` and contributes 0, so the job is `recommended` with a near-zero score. ADR-058 sets aside only jobs with a fired gate; a low score alone never moves a job.

**Decision (proposed):**
1. **New role families (taxonomy v2).** A new migration adds terms to `role_family` and bumps the taxonomy version (the v1 seed constants stay frozen): `finance_accounting`, `legal_compliance`, `hr_recruiting`, `marketing_communications`, `operations_admin`, `design_creative`. `sales_account_management` and `customer_support` already exist. The list is a starting point from the audited data; the owner confirms it (question 1).
2. **Stances.** A new family has no stance in the existing intent, so it scores 0 and never gates. The owner sets them to Rejected in the Search Intent (the existing screen lists every taxonomy term). No stance is changed automatically and no intent revision is written by the migration. A family that every job lacks stays unknown.
3. **New extraction prompt version.** The extraction prompt lists the allowed families, so `extract-v2` (the current one is `extract-v1`) includes the new terms; the model then classifies finance jobs as `finance_accounting` and G1 fires when the owner rejected it. Old extractions stay (append-only); re-extraction of open jobs is a separate, explicit owner action because it costs model time (question 2).
4. **Low-fit floor for "Set aside".** One owner setting, `schedule_setting.set_aside_below_fit` (integer 0 to 100; `0` means off; default `20`; edited next to the daily schedule), not a field of the intent. In the inbox, a job whose latest evaluation for the chosen intent is `recommended` but has `fit_score < set_aside_below` is listed under **Set aside** with the reason "Fit below your floor (N)". Evaluations are not rewritten and nothing is stored per job: like ADR-058 the partition follows the stored evaluations and the intent, so changing the floor moves jobs at once. Jobs without an evaluation are never set aside (they have no verdict). Counts, tabs and the `set_aside` filter use the same rule.
5. **Not a gate.** The floor is a display rule and does not change the score or `recommendation`; a low score is not a hard-constraint mismatch (ADR-021, ADR-026). `matching-v1.5` is therefore unchanged; no rescore is needed for point 4, only for point 3 (new extractions, then new evaluations).
6. **Updated jobs (amendment, 2026-10-13, requested by the owner).** A `not_recommended` job is set aside also when the source changed it since the owner last saw it (`updated_unread`): the **Set aside** section and its count cover unread and updated-unread jobs, and "To review" leaves them out. The low-fit floor still never sets an updated job aside. Display rule only; no score, policy or stored data changes.
6. **Not done here:** keyword rules on titles (rejected: ADR-021 forbids keyword-rule fallbacks), and an "unknown role" gate (an unclassified job might still be relevant).

**Why:** the family list is the cause (the model has nowhere to put finance jobs), so adding families fixes the source and keeps the score a function of stored judgements. The floor catches what stays unclassified or unplaced without inventing a gate, and keeps the owner able to open any job.

**Consequences (if approved):** migration for taxonomy v2; extraction prompt version bump; intent schema gains `set_aside_below` (schema version, default for existing intents); `repositories/inbox.py` set-aside predicate and counts; Search Intent screen (floor field) and the Set aside rows (reason text); `make api-client`, `make docs-schema`; doc 13 and CLAUDE.md updated. Expected effect on the audited data: the 23 finance jobs and other near-zero-fit items leave "To review".

**Questions for the owner:**
1. Which families should be added (the six above, fewer, or others you see in your inbox)?
2. After the new prompt, re-extract the open jobs now (model time) or only new ones?
3. Floor default: `10`, another value, or off until you set it?
4. Should the floor live in the Search Intent (per intent, versioned) or be a single inbox setting?

### ADR-061 — Ignore a company: its offers go to Ignored

**Status:** requested and **approved by the owner on 2026-10-12** (answers: new offers enter as Ignored; undoing restores only what the company ignore moved; the action lives on the Companies screen and dossier). Touches the inbox semantics (LLD section 3).

**Finding:** the owner does not want to work for some employers (for example crypto companies) and ignoring their offers one by one is endless.

**Decision:**
1. **Personal state, like follow (ADR-053):** table `company_ignore` (`owner_id`, `company_id`, unique together, `created_at`; no soft delete, undoing deletes the row). Idempotent `PUT`/`DELETE /api/v1/companies/{company_id}/ignore`.
2. **Ignoring** moves every open item of the company's opportunities in `unread`, `read` or `updated_unread` to `ignored` at once, with action `ignore`, actor `system` and `ignore_reason = company_ignored` (a code, never free text). Opportunities with no inbox item yet get one that is ignored. Archived, applied and already ignored items are left alone.
3. **New offers** of an ignored company are surfaced already `ignored` (same reason), so they never appear as unread and never enter the digest as new.
4. **Undoing** restores (action `restore`, actor `system`, to `read`) only the items that are `ignored` with reason `company_ignored`; items the owner ignored by hand keep their state.
5. Nothing changes in matching, scoring or collection; evaluations are still made, so undoing loses nothing. A shortlisted item stays shortlisted (the flag is independent).

**Consequences:** migration for `company_ignore`; `is_ignored` on the company list and the dossier; ignore/stop-ignoring buttons on both; `make api-client` and `make docs-schema`.

### ADR-062 — The daily schedule runs at several times of the day

**Status:** requested and **approved by the owner on 2026-10-12** (times 09:00, 12:00 and 16:00 to start; the Sources screen adds and removes times). Extends ADR-017 and ADR-031.

**Finding:** one run a day left the inbox without new jobs for up to 24 hours, and boards publish through the day.

**Decision:**
1. `schedule_setting.run_time_local` becomes `run_times_local`, a `time[]` of one to twelve local times, stored sorted and without seconds. Migration 0019 turns the existing time into a one-item list (the way back keeps the earliest time). The time zone stays one value for all times.
2. `PUT /api/v1/settings/schedule` takes `run_times_local` (a list; empty, repeated or more than twelve is 422). `GET` returns the sorted list, `next_run_at` is the nearest future time.
3. Every time is its own occurrence: the run is unique per `(owner, scheduled_for)` as before, so a time creates exactly one run however many workers poll.
4. **Catch-up, not bursts:** the worker starts only the latest time that has passed, and only within the existing 12 h window. After an outage through 09:00 and 12:00 it starts one run, not two. A time that passed before the schedule was saved never runs.
5. Job boards keep their minimum interval (60 to 360 minutes). A scheduled run skips a board contacted too recently (`skipped`), so a 360-minute board runs at some of the times and not all.
6. No change to collection, matching or the inbox.

**Consequences:** migration 0019; `make api-client` and `make docs-schema`; the Sources schedule card lists the times with add and remove.

### ADR-063 — Sources are collected at the same time, and job boards read only the latest days

**Status:** requested and **approved by the owner on 2026-10-12** (parallel sources; a window of about 4 days; boards never close postings by absence). Amends ADR-042 and ADR-049 (collection, closing); extends ADR-062.

**Finding:** a manual run on 2026-10-12 spent 15 minutes on Arbeitnow (6 requests a minute, up to 100 pages) while the 36 other sources waited behind it, because sources ran one after the other. With three runs a day this would repeat every time. The daily runs also make older postings duplicates of what is stored.

**Decision:**
1. **Parallel sources.** The sources of one run are collected at the same time, at most 8 at once (`DEFAULT_MAX_PARALLEL_SOURCES`). Each source already uses its own short database sessions and its own rate limit, so nothing is shared. A source that crashes is recorded as failed and never stops the rest; the run status rules are unchanged. The heartbeat is refreshed after each source.
2. **Company creation is serialised.** `company.name_normalised` is not unique, so two job boards naming the same company could create it twice. A job board's companies are now found or created first, in their own short transaction, under a transaction-scoped advisory lock per normalised name, taken in sorted order (no deadlock).
3. **Short window.** The catalogue default of `max_age_days` for job boards is 4 days (was 30). The scan already stops at the first page whose postings are all older than the window (newest-first boards), so Arbeitnow goes from about 100 pages to about 10. The stored value of existing boards is changed by the owner (or by SQL on the development database); the limit remains editable from 1 to 365 days. Company boards keep their own default (opt-in filters, 30 days) because they list everything in one request.
4. **No closing by absence on job boards.** With a window of a few days, a posting that is not seen has simply aged out of the window, so job boards never close postings by absence (decided by the owner). Company boards still close a posting after two consecutive successful runs without it (ADR-045). Consequence: postings from job boards stay open until the owner archives or ignores them.
5. The minimum interval between runs of a board (60 to 360 minutes) is unchanged.

**Consequences:** `CollectionService(max_parallel=...)`; `CompanyRepository.get_or_create_many`; catalogue default; no migration, no API change except the default filters returned by the catalogue.

### ADR-064 — Pre-application: strengths, positioning and a cover-letter base written on request

**Status:** requested and **approved by the owner on 2026-10-12** with these answers: local model only; the letter in the language of the posting; every draft kept (append-only). It sends the owner's profile facts to a model for the first time outside CV import, but only to the local model, so no data leaves the machine (ADR-046). It changes no scoring semantics.

**Finding:** the inbox ends at the decision to apply. Preparing the application (what to stress, how to introduce oneself, a first letter) is done by hand for every job worth applying to.

**Decision:**
1. **On request only.** A button "Pre-application" in the inbox detail asks the model for a draft of one job; nothing is generated by the worker and nothing is generated for jobs the owner did not ask about. There is no auto-apply and no form filling (out of scope).
2. **Prompt `application-v1`.** The prompt holds the company, the title, the posting (bounded, ADR-044 limit) and the facts of the owner's profile: headline, years of experience, languages, skills (name, level), experience (title, organisation, period, summary), education and certifications. It holds no contact details (the profile has none) and no name. The model answers JSON: `strengths` (3 to 6 items, each a `point` and the profile `evidence` it rests on), `positioning` (how to introduce oneself: 2 to 4 sentences), `gaps` (0 to 4 honest requirements the profile does not show, with how to address them), `cover_letter` (200 to 350 words, no placeholders other than `[Your name]`) and `letter_language` (`pt` or `en`).
3. **Language.** The strengths, positioning and gaps are written in English like the summary; the cover letter is written in the language of the posting (Portuguese of Portugal or English; English for any other language).
4. **Faithfulness.** The prompt allows only facts present in the profile and the posting and forbids invented experience, employers, numbers and skills. Because free prose cannot be quote-checked, the code checks shape (bounds, language code, required parts), and every strength's `evidence` must contain a skill name, organisation or title that exists in the profile facts; a strength that fails that check is dropped, and fewer than three remaining strengths makes the attempt `failed`. The screen labels the draft "AI draft: check every claim before sending" and the gaps are shown with it.
5. **Model.** The local jobs connection with the larger local model chosen for directions (ADR-057, as the summaries, ADR-059), never a remote one, no fallback. Without a local model the owner is told to choose one (422); a model that is down is 503 and stores nothing.
6. **Storage.** New append-only table `application_draft` (job snapshot, profile revision, provider, model, prompt version, `draft_json` validated with `schema_version`, latency). Only usable drafts are stored: a failed attempt is a 503 for that call and leaves no row. Every request creates a new row (the owner may regenerate and compare); the detail shows the newest successful draft and the date, and can list earlier ones. Which profile: the current revision of the first enabled intent's profile (the one that scores the jobs), else the owner's first profile with a revision; without a saved profile the owner is told to save one (422). A draft never feeds the score, the inbox state or the digest.
7. **API.** `POST /api/v1/jobs/{job_posting_id}/application-draft` creates a draft and returns it; `GET /api/v1/jobs/{job_posting_id}/application-drafts` lists them, newest first. The inbox detail `GET` is unchanged (the drafts load on demand when the panel is opened).
8. **Copy, not edit.** The letter is shown as plain text with a "Copy" button; editing happens in the owner's own editor, so the app stores no edited documents.

**Why:** the profile is the one canonical source of facts about the owner, and the posting is already analysed locally; combining them in a bounded, evidence-checked draft saves the first hour of every application without ever letting the model state something the owner cannot defend.

**Consequences:** migration 0020 (`application_draft`, append-only trigger); `make api-client`, `make docs-schema`; one longer model call (tens of seconds for a 27B model) per click, shown as a busy button; frontend section in the inbox detail. Open and not decided: tone presets, a CV tailored per job, and storing the owner's edited letter.

### ADR-065 — Dashboard widget summary and LAN exposure of the API

**Status:** requested by the owner on 2026-10-13 (a Homepage widget); the LAN bind was **approved by the owner on 2026-10-13**.

**Finding:** the owner runs Homepage (gethomepage) on another host of the LAN and wants to see, without opening Jobs Radar, how many jobs are "To review", how many of them reach a fit threshold, and whether the stack is up. The API listens on `127.0.0.1` only (ADR-009), so Homepage cannot reach it.

**Decision:**
1. **Endpoint.** `GET /api/v1/widget/summary?fit_min=65[&search_intent_id=N]` (read-only, no personal data): `to_review` (unread without the set-aside ones plus updated-unread: the Inbox badge number), `to_review_high_fit` (of those, fit >= `fit_min`; unscored jobs never count), `fit_threshold`, `best_fit` (highest fit among "To review", or null), `followed_recommended` (offers of the same set from followed companies whose latest evaluation is recommended), `status` and `components` (the `/readyz` result). Scores come from the given intent, by default the first enabled one, as in the inbox. It always answers 200 so the widget can show the state; `/readyz` stays the probe.
2. **Threshold.** `fit_min` is a query parameter (0-100, default 65), set in the Homepage configuration; no new setting or table.
3. **Exposure.** The owner sets `JOBS_RADAR_API_BIND` to the LAN address of the host. The whole API (still without authentication, ADR-009) is then reachable from the LAN; this stays a per-installation choice in the untracked `.env`, the default remains `127.0.0.1`. No other change to the exposure rules.

**Why:** a counter on the dashboard the owner already looks at is the only notification surface that fits the "no external notifications" scope (the in-app digest stays the source of truth).

**Consequences:** no migration; `make api-client`; the Homepage snippet is in `docs/operations/homepage-widget.md`.

### ADR-066 — A rejected primary role family gates the job (`matching-v1.6`)

**Status:** requested and **approved by the owner on 2026-10-13**. Amends ADR-026 (gate G1).

**Finding:** "Senior Sales Engineer, Enterprise - German Speaking" (Fivetran) scored 54 and `recommended`. The model listed `sales_account_management` (rejected by the owner) first and `consulting_integration` (acceptable) second; G1 fired only when *every* family was rejected, so the second family hid the first. A required language the owner does not work in also cost nothing because the owner's intent had `reject_unspoken_required` off.

**Decision:**
1. Gate G1 also fires when the **primary** role family is rejected. The primary family is the first one listed by the model that clears the confidence floor (the extraction prompt asks for the best-fitting family first). The dimension is then a mismatch.
2. A rejected family listed after an acceptable or preferred primary one still does not gate; the best stance still sets the dimension strength.
3. Policy version `matching-v1.6`; earlier evaluations are kept and a rescore creates new ones. No prompt change, so no re-extraction.
4. The language gate G7 needed no code change: the owner switched `languages.reject_unspoken_required` on in the Search Intent (a new intent revision).

**Why:** a job whose main activity is one the owner rejected is not made acceptable by a secondary label.

**Consequences:** no migration; `make api-client`; docs 13 updated.

### ADR-067 — `extract-v3`: the model must answer the role families and skills

**Status:** requested and **approved by the owner on 2026-10-13**. Amends ADR-044 and ADR-060 (extraction prompt version).

**Finding:** 33% of the stored extractions (1859 of 5611 `extract-v2`, the same share in `extract-v1`) had no role family. The model was not failing: it left the key out, because the JSON schema sent to Ollama listed only the evidenced attributes as `required` (`role_families` and `skills` have defaults in the validation model). Without a family the role dimension is unknown and gate G1 (ADR-066) cannot fire. Re-running six such jobs with both keys required gave plausible families for all of them.

**Decision:** `role_families` and `skills` are `required` in the schema sent to the model (an empty list is still valid; the validation model is unchanged, so stored extractions keep validating). Prompt version `extract-v3`. Re-extracting every open job was started and stopped by the owner (about 6 jobs per minute with the local model, 13 hours): `extract-v3` applies to jobs without an extraction and to the 356 already re-extracted, while jobs with a successful `extract-v2` extraction keep it (`EXTRACTION_ACCEPTED_PROMPT_VERSIONS`; emptying it re-queues them). Of the 356, 4% have no role family (36% of the same jobs under `extract-v2`).

**Why:** a schema change alters what the model returns, so it needs a new version to keep results reproducible.

**Consequences:** no migration; local extraction of every open job runs again (hours); older extractions are kept.

### ADR-068 — A bare country or region next to a remote marker limits remote work (`matching-v1.7`)

**Status:** requested and **approved by the owner on 2026-10-13**. Amends ADR-056 and ADR-058.

**Finding:** Linear's "Senior / Staff Product Engineer" (Ashby) was `recommended` (44) although its board location is `North America` and the owner lives in Portugal. The company publishes the same text twice, once with location `Europe` and once with `North America`; the text says "open to candidates based in the US and Europe" in both, so the structured location is the only signal that tells them apart. The Ashby adapter stores the places `["North America", "Remote"]`. `source_remote_countries` required every place to contain a remote word (`India (Remote)`, `Remote US`), so `North America` was read as an office and the source limited nothing. Over the open jobs, 56 recommended ones had only countries or regions plus a remote marker; 33 of them exclude Portugal.

**Decision:**
1. When at least one place of the source carries a remote word (including the bare `Remote` some adapters add because the board flags the job as remote), the other places count as remote places if every one of them is a country or a region the table knows (`North America`, `Europe`, `United States`, `Canada`). They then limit the remote regions exactly as `India (Remote)` does (ADR-056).
2. A city, an office name or an unknown place next to a remote marker still means "no limit" (unchanged), and so does a list with no remote marker at all.
3. Policy version `matching-v1.7`; earlier evaluations are kept and a rescore creates new ones. No prompt change, so no re-extraction.

**Why:** a board that flags a job as remote and names only countries or regions is saying where the work can be done from; ignoring it let the model's guess from generic text override a structured field.

**Consequences:** no migration; `make api-client`; docs 13 and CLAUDE.md updated. The effect is limited to places made of countries or regions next to a remote marker; other boards (Lever, Greenhouse, SmartRecruiters) benefit when they use the same patterns. Not done here: telling the extraction prompt to prefer the structured location, and showing the source region next to the text region in the evidence.

### ADR-069 — The location evidence shows the board's places next to the text's regions (`matching-v1.8`)

**Status:** requested by the owner on 2026-10-13 (point 3 of the ADR-068 follow-up). Amends ADR-068.

**Finding:** when the board's location and the posting text disagree (Linear: `North America` against "open to candidates based in the US and Europe"), the owner could only see the final regions and a note appended to the quote, not which side said what.

**Decision:**
1. The evidence of the location dimension for remote work adds `source_places` (the board's places, as stored) and `text_regions` (the regions the model read, after country names became codes and before the board limited them) whenever the posting has source places; `job_regions` stays the regions the score used.
2. The inbox detail shows them in the evidence popover as "Board location", "Regions in the text" and "Open from".
3. Evidence only: no score, gate or band changes. The policy version still moves to `matching-v1.8`, because the evidence is part of the stored, append-only evaluation and the unique key includes the version; a rescore stores the new evidence and keeps the old evaluations.

**Consequences:** no migration; `make api-client`; docs 13 unchanged apart from the version.

### ADR-070 — Follow a company from its website and careers URLs

**Status:** **approved by the owner on 2026-10-13 and implemented the same day (phases 1, 2 and 3; see the implementation note below)**; requested the same day (option A; layers 2 and 3 added at the owner's request). Phase 1 is next, after the mock-up `docs/design/follow-company-mock.html` is accepted; phases 2 and 3 each wait for the owner's go-ahead. Implements item 2 of ADR-055 (detection from a URL, which was approved there but not built) and amends item 4 of ADR-055 ("a company without any source cannot be created by hand"). It changes how collection sources are created and adds outbound requests to owner-typed addresses, so it needs the owner's approval first (ADR-012, ADR-054, ADR-055).

**Finding:** the only way to put a company on the Companies screen is to add a source for it, which needs the ATS type and its identifier (the last part of a Greenhouse, Lever, Ashby or SmartRecruiters address, or the Eightfold host). The owner knows the company's name, its website and its careers page, not the ATS, and has to inspect the careers page by hand. Example: Datadog's careers page is a front for Greenhouse board `datadog`. The website of a company is also the key of the dossier (ADR-054), but today it is found by chance or typed afterwards in a second step.

**Decision:**
1. **One form, two addresses.** A "Follow a company" action on the Companies screen asks for the company **website** (required; it feeds the dossier and the open-data enrichment exactly as in ADR-054) and the **careers page address** (required; where the offers are published), the company **name** (required) and a checkbox "Keep only postings that match my areas and location" (ADR-051 filters), **on by default**. Nothing is sent anywhere until the owner confirms.
2. **Detection, no AI.** A fixed detector (`adapters/sources/detector.py`) turns the careers address into a proposed source, in this order:
   a. **Address patterns, no request:** `boards.greenhouse.io/<token>`, `job-boards.greenhouse.io/<token>` (and the `eu` variants), `jobs.lever.co/<id>`, `jobs.ashbyhq.com/<id>`, `jobs.smartrecruiters.com/<id>` and `careers.smartrecruiters.com/<id>`.
   b. **The careers page itself** when the address is the company's own: one GET (redirects followed only to the company's registered domain or to the ATS hosts above, each hop re-validated) and a search of the final address, of the links, iframes and scripts for the same ATS markers (for example `greenhouse.io/embed/job_board?for=<token>`, a `gh_jid` parameter, `boards.greenhouse.io/<token>` links). For an Eightfold site the careers host is probed with the existing validation call.
   c. **Validation before proposing:** every candidate is checked with the existing adapter `validate` (the board must exist and answer), so a proposal is always a real board with its open-posting count and name.
   Outcomes: `detected` (one candidate), `ambiguous` (several; the owner chooses), `unsupported` (no known ATS: Workday, Teamtailor, iCIMS, own page), `unreachable` or `blocked` (refused, robots.txt, too large, timeout) and `script_only` (the page needs JavaScript; ADR-055 keeps that out of scope).
2b. **Collection layers** (the detector proposes the first layer that works for the careers address; implementation is phased and each phase is useful on its own):
   - **Layer 1, ATS API (phase 1).** The known systems of item 2 (`greenhouse`, `lever`, `ashby`, `smartrecruiters`, `eightfold`): one list request per run, conditional requests, stable.
   - **Layer 2, structured postings on the company's own site (phase 2, new source type `page_jsonld`).** Many employers publish each posting page with a schema.org `JobPosting` in JSON-LD, because Google for Jobs requires it. The posting list comes from the sitemap (`Sitemap:` lines of `robots.txt`, then `/sitemap.xml`; entries whose address looks like a posting), otherwise from the same-domain links of the careers page; each posting page is read with one GET and its `JobPosting` is parsed (title, description, `datePosted`, `validThrough`, `jobLocation`, `employmentType`, `baseSalary`, canonical URL). Deterministic, no AI. Detection proposes this layer only when at least one sampled posting page holds a valid `JobPosting`. Bounds: at most 200 posting pages per run (`partial` beyond, never closing postings, ADR-049.5), the sitemap's `lastmod` skips pages that did not change, spaced requests (30 a minute by default). A posting closes after two complete runs without it, as for company boards (ADR-045).
   - **Layer 3, a configuration proposed by the local model and approved by the owner (phase 3, source type `page_config`; this is ADR-055 item 3).** Only for server-rendered pages that have neither a known ATS nor JSON-LD. The local model (ADR-046, never a remote one) reads the page text and proposes a schema-validated configuration (listing address, how a posting is delimited, where title, location and link are, how to page); the owner reviews it with a preview of the postings it would read and approves it; later runs use a fixed reader with **no AI**. The model never generates or runs code. A page that stops matching fails visibly with `schema_changed`, and a new proposal can be requested (previous configurations are kept). Built only if phase 2 leaves too many companies uncovered.
   - **Out of scope:** pages whose postings are loaded by JavaScript from a private API (outcome `script_only`); a headless browser or reading such private APIs would be a separate decision.
   Layers 2 and 3 keep every rule of item 7 (owner-typed addresses only, guarded client, `robots.txt`, same registered domain, bounds) and every posting still goes through the normal pipeline (normalise, dedupe, snapshot, evaluation); the posting URL is the stable identity. They also create the company's postings next to those from job boards, which `dedup-v1` (ADR-023) links when they are the same opportunity, preferring the employer's own listing.
   **Live check of 2026-10-13 on the owner's examples** (read-only, three GETs each, nothing stored): `jobs.ashbyhq.com/mistral.ai` is layer 1 (Ashby identifier `mistral.ai`, 213 postings from the posting API); `wise.jobs` is layer 2 (no ATS markers; every posting page has a `JobPosting` JSON-LD and `/vacanciessitemap.xml` lists about 400 pages; `robots.txt` disallows only search and account paths); `careers.adyen.com` is `script_only` (a Nuxt application whose postings are searched client-side through Algolia, no JSON-LD, no postings in the HTML). Adyen would be followed with its website and careers address but without automatic collection.

3. **Preview, then confirm.** `POST /api/v1/companies/onboarding/detect` (no writes) returns the normalised website, the careers address and the candidates. `POST /api/v1/companies/onboarding` creates everything in one transaction: the company (matched by normalised name, so a company already known from a job board gets the source attached instead of a duplicate), its website through the existing `set_website` rules (public host only, job-board addresses refused), `careers_url`, the chosen source through the existing `SourceService.add` path (same validation, defaults and rate limits), and the **follow** state (ADR-053). With a source, a manual run of that source is **queued at once** (the worker executes it, ADR-042), and the ADR-051 filters are saved with the source when the checkbox is on.
4. **Unsupported is still useful.** With outcome `unsupported`, `unreachable`, `blocked` or `script_only` the owner may still confirm: the company is created with its website and careers address and followed, with no source and the message "No automatic collection for this careers page". The dossier works (ADR-054) and the Companies screen links the careers page. A "Detect again" action repeats the detection, so a system supported later (Workday, Teamtailor, a generic page, ADR-055) is picked up without re-typing anything.
5. **Name.** Required in the form and always the company's name and source display name (the ATS name is not used to override it).
6. **`careers_url`.** The existing column `company.careers_url` (no code writes it today) stores the confirmed address. The dossier reader (ADR-054, `services/enrichment.py`) keeps its rule of reading only pages of the confirmed registered domain, so a careers address on an ATS host is displayed but not read.
7. **Privacy and security.** Only addresses typed by the owner are requested; everything goes through `GuardedHttpClient` and `UrlGuard` (HTTPS by default, no link-local, metadata or private-network targets, no redirect into a blocked target, bounded body size and time, `robots.txt` honoured, no cookies, no JavaScript, at most five requests per detection). No page text is stored or sent to any model. The tests use synthetic HTML and `respx` and make no network request; `make smoke` gains one real detection.
8. Nothing changes in matching, scoring, the inbox, the ADR-051 filters or the follow semantics. Collected jobs of a source created this way are indistinguishable from those of a source added in Sources.

**Why:** the owner's list of companies to watch is a list of names and addresses, not of ATS identifiers. The identifier is already in the careers address or in its page, so the system can find it and the owner only confirms. Requiring both addresses keeps detection simple and avoids guessing a careers page from a home page.

**Consequences:**
- New: `adapters/sources/detector.py`, `services/company_onboarding.py`, two endpoints, a "Follow a company" card or dialog on the Companies screen (mock-up in `docs/design/` before the screen is built), `make api-client`, `make docs-schema`.
- No migration is expected (`company.careers_url`, `source_configuration.company_id` and `company_follow` exist); confirm when designing.
- Risks: a careers page that embeds several ATS (an acquired company) is reported as `ambiguous`; the ATS markers are undocumented conventions and may change, which degrades to `unsupported` and never to a wrong source because of step 2c; a name that differs from the one on the job boards creates a second company (the duplicate-company merge is not part of this ADR).
- Phases: 1 (form, ATS detection, follow, dossier) first; 2 (`page_jsonld`) next, with one migration for the new `SourceType` values; 3 (`page_config`, review screen) only if needed. Phase 2 and 3 amend ADR-055 item 3 (the generic careers page is split in a deterministic layer and a model-assisted one).
- Not done here: batch import of many companies (option B, a later ADR if wanted), Workday and Teamtailor adapters (ADR-055 item 1), JavaScript-rendered pages.

**Owner decisions (2026-10-13):** (a) collect the new source immediately; (b) the filter checkbox is in the form and on by default; (c) the company name is required.

**Implementation note (2026-10-13, all three phases):**
- Detection: `domain/careers_markers.py` (pure rules), `adapters/sources/detector.py`, `adapters/sources/robots.py`. A detection is at most one page request, `robots.txt`, and three board validations (plus the structured-postings probe, which reads the sitemap and three posting pages). `looks_script_only` decides `script_only`: no posting-like link in the HTML and an application-shell marker (or a nearly blank page). Checked live the same day: `jobs.ashbyhq.com/mistral.ai` is detected as Ashby, `wise.jobs` as structured postings, `careers.adyen.com` as `script_only`.
- Layer 2 (`page_jsonld`, `adapters/sources/page_jsonld.py`): the identifier is the careers host and path (`wise.jobs`). The sitemap content is hashed into the ETag; an unchanged sitemap reads no posting page. At most 200 posting pages per run, newest first by `lastmod`; a page that fails makes the run partial and clears the ETag. An expired `validThrough` is not a posting. Default pace 60 requests a minute.
- Layer 3 (`page_config`): migration 0022 adds the append-only table `page_reader_configuration` (the newest revision of a source is the active reader, earlier ones are the history). `PageReaderConfig` holds CSS selectors only (`schemas/page_reader.py`); `adapters/sources/page_config.py` is the fixed reader (at most 100 posting pages per run, `schema_changed` when nothing matches). `services/page_reader_proposal.py` asks the local model (the larger model chosen for career directions, prompt `reader-v1`, never a remote one) for the selectors, forces the listing address, and verifies the answer with the same reader on the fetched page; an answer that finds no posting is not offered. The owner approves it in the follow dialog; a new reader of an existing source is approved with `PUT /api/v1/sources/{id}/reader`.
- API: `POST /api/v1/companies/onboarding/detect`, `POST /api/v1/companies/onboarding`, `POST /api/v1/companies/onboarding/propose-reader`, `POST /api/v1/sources/{id}/reader/propose`, `PUT /api/v1/sources/{id}/reader`. `CompanySummary.has_source` and `BoardRead.{source_type, version, last_*}` feed the "Not collected" chip and the Collection card.
- `SourceType` gains `page_jsonld` and `page_config` (migration 0021), both company boards for `dedup-v1` (the employer's own listing is preferred). `SourceErrorClass.SCHEMA_CHANGED` is new.
- Not done: Workday and Teamtailor adapters (ADR-055 item 1), batch import (option B), JavaScript-rendered pages.

### ADR-071 — The low-fit floor defaults to 30 and is set in Scoring weights

**Status:** approved by the owner on 2026-10-14. Amends ADR-060 (default and location of the setting); no scoring or policy change.

**Decision:**
1. The default of `schedule_setting.set_aside_below_fit` goes from 20 to 30. Migration 0023 changes only the column default: rows that already exist keep the owner's value.
2. The setting stays owner-wide in `schedule_setting` (no intent revision, no per-intent value). The control moves from the Daily schedule card of the Sources screen to the Scoring weights section of Profile & intent: a 0–100 slider below the weights with its own "Save limit" button (0 = off). The schedule card no longer shows it and sends the stored value back unchanged.
3. Meaning is unchanged (ADR-060): recommended jobs scored below the floor are listed under "Set aside" instead of the inbox; unscored jobs are never set aside; jobs set aside by a hard gate (ADR-058) are independent of the floor.

### ADR-072 — We Work Remotely as a job board (public RSS feeds)

**Status:** approved by the owner on 2026-10-14 (the owner states that everything in Jobs Radar is personal use and asked for this board). Extends ADR-049; reverses the exclusion recorded in R-00173 for this one board.

**Context:** R-00173 excluded We Work Remotely because its API terms are reported (through a search summary; the page answers 403 to automated readers) to forbid "scraping, copying, saving, or storing" the data and to require applying through its site. The board does publish public RSS feeds (`robots.txt` allows them, no key). The owner states that everything in Jobs Radar is personal, single-user and local, and accepts the risk.

**Decision:**
1. We Work Remotely joins the fixed catalogue (`SourceType.WEWORKREMOTELY`, migration 0024). It is a job board in the sense of ADR-049: filters, the location scope from the profile (ADR-049.11), attribution and the minimum run interval apply unchanged.
2. The adapter (`adapters/sources/weworkremotely.py`) reads the RSS feeds only: the newest-postings feed and the category feeds (ten requests a run, 10 a minute, at least 60 minutes between runs, as the feeds are refreshed about hourly). Nothing else on the site is requested; `robots.txt` is respected.
3. The company comes from the title (`Company: Role`), falling back to the `Headquarters:` line; a posting with neither is skipped. The `region` and `country` fields give the eligibility: no country list and "Anywhere in the World" is worldwide, a country list is those countries, a region name ("Europe Only", "Remote - Americas", "USA Only") is expanded with the existing region groups, and anything unreadable is kept for the later judgement.
4. Use stays personal: postings are stored and evaluated locally, shown with a link back and the attribution text, and are never exported or published. The catalogue and `docs/legal/data-sources.md` state the reported terms and that they were not read by the project. If the application is ever made available to anyone else, this board must be removed or its terms confirmed first (ODR-007).
5. Not done: feed items carry no salary or structured company data; the board's JSON API is not used.
6. **Window of 30 days** (owner, 2026-10-14, after a first run kept 20 of 112 eligible postings): the default `max_age_days` of this board is 30 instead of 4. The feeds list only open postings and hold about 330 in all, so ADR-063's short window would drop most technical ones. A first run with 30 days keeps about 100.

### ADR-073 — Contract work first: engagement kind, day rate and contract job boards

**Status:** accepted by the owner on 2026-10-14 (part A implemented; part B, the sources, follows). It was first requested as "ADR-021"; that number is taken (AI-first hybrid evaluation), so the next free one is used. Extends ADR-026 (stance model), ADR-044 (extraction), ADR-049 (job boards).

**Context:** the owner looks for contract work and wants to find contract offers, especially those that state a daily rate. Today `engagement_type` is extracted (taxonomy `employee_permanent`, `employee_fixed_term`, `contractor_b2b`, `freelance`, `internship`) and scored, but it is not shown on the inbox row, cannot be filtered, there is no term for a contract placed through an agency, and the pay is not visible on the card. The job boards in the catalogue carry few contract offers.

**Decision (proposed):**
1. **Taxonomy v3** adds the `engagement_type` term `contractor_agency` (contract through an agency or umbrella company, paid by day or hour, no own invoicing). `contractor_b2b` and `freelance` stay; the prompt (`extract-v4`) defines the three contractor kinds and the fixed-term employee so the model does not blur them. Open jobs are re-queued as for ADR-060. Existing evaluations are kept (append-only).
2. **Display:** the inbox row and the detail show the engagement kind as a text badge (never colour alone) and the pay on the card: the stated day rate (`€ 450–550 / day`) or the words `Rate not stated` for a contract offer with no rate. Permanent offers show the salary or nothing.
3. **Filter:** `GET /inbox` gets `engagement` (multi-value: permanent, fixed term, contractor kinds, internship, unknown) and `rate` (`stated`, `not_stated`). Offers without a stated rate are shown by default (owner: "rate not stated"). A display rule only; no score, policy or stored value changes.
4. **Currency:** day rates are shown and compared in euro only (owner, 2026-10-14). A rate in another currency is shown as written and never compared; no conversion is added.
5. **Scope:** EU and remote work possible from Portugal; Switzerland is acceptable but not preferred. This is the owner's Search Intent (regions and stances), not a code rule.
6. **Sources:** a research document (R-xxxxx) evaluates contract-focused boards (for example freelance.de, Freelancermap, Malt, agency job feeds) for API, feed or terms that allow reading. Only boards that pass join the catalogue, each by its own ADR/adapter as in ADR-049/072; HTML scraping of boards whose terms forbid it stays out unless the owner decides otherwise per board.

7. **Older intents.** A closed group of an intent must list every term, but an intent saved before `contractor_agency` existed does not. Terms added after taxonomy v1 are therefore optional in closed groups (`schemas.intent.later_terms`), and the matching view gives an unlisted one the stance *acceptable*, which is what the form already shows for it, until the owner chooses. A stance the owner set is never overridden.
8. **Re-extraction (owner, 2026-10-14):** a new prompt or taxonomy re-extracts only jobs still in the inbox and new ones. A snapshot that has a successful extraction and whose opportunity is ignored or archived is not queued again; earlier evaluations stay valid (`extract-v3` joins the accepted prompt versions).
9. **Filter semantics:** `engagement` matches known engagement types only; `unknown` matches jobs with none known (including jobs not extracted yet). `rate=stated` means a disclosed pay with a range; `rate=not_stated` means contract work (B2B, freelance, agency) with no stated pay, so a permanent or unknown offer without pay is never "rate not stated".

10. **Re-extraction limited to the main inbox (owner, 2026-10-14, amends 8):** the first migration queued about 2,600 re-extractions, almost all of jobs the inbox sets aside (a gate fired or the fit is below the floor, ADR-058, ADR-060). A snapshot that already has a successful extraction is also left alone while its opportunity is set aside, by the same rule as the "Set aside" tab (latest evaluation not recommended, or fit below `set_aside_below_fit` unless the source changed the job). Rows already queued stay waiting and are not claimed; they resume if the job leaves "Set aside". Snapshots never extracted are claimed before any re-extraction.

**Not decided:** a dedicated "Contracts" view with rate statistics by stack (owner: the filter is enough for now); currency conversion.

**Consequences:** one taxonomy version, one migration (term and prompt version), one API change (`make api-client`), frontend badge and filters. Order: part A (steps 1–3) first, then the source research.

### ADR-074 — Working Nomads and Remote OK as job boards

**Status:** approved by the owner on 2026-10-14. Extends ADR-049; follows research R-00176.

**Context:** the owner looks for contract work and the offers on these two free boards are largely independent-contractor work. Both publish a public JSON feed with no key (R-00173 wave 2).

**Decision:**
1. Both join the fixed catalogue (`SourceType.WORKINGNOMADS`, `SourceType.REMOTEOK`, migration 0026) as job boards of ADR-049: filters, the location scope of ADR-049.11, attribution and a minimum run interval of 60 minutes apply unchanged.
2. Working Nomads (`/api/exposed_jobs/`): one answer holds every open posting; it has no id (the URL is the identifier) and no pay field. Remote OK (`/api`): about 100 newest postings; the first element is a legal notice and is not a posting; `salary_min`/`salary_max` are annual and `0` means not stated; no currency is given, so the stated range is appended to the description as such and never compared.
3. Both boards give the place as one free text (`Worldwide`, `Europe`, `USA`, `Spain, Portugal`, a time zone). `adapters/sources/place_text.py` reads it: empty or worldwide words mean anyone, named countries and regions limit the work to them, and any unreadable part keeps the posting for the later judgement. The contract kind is not a field of either board: it comes from the text through the extraction (ADR-073).
4. Windows: Working Nomads reads 30 days (a small feed of open postings, as ADR-072.6) and Remote OK 7 days (only the newest postings are listed).
5. Terms: Remote OK requires a link back with follow and the source named, and no logo (shown as attribution text). Working Nomads states no terms that were found; the link back to the original posting is kept and the poll is at most hourly.
6. **Posting page of Working Nomads (owner, 2026-10-14):** the feed's `url` (`/job/go/<id>/`) redirects to the employer's application form, so it is the apply link and the identifier, not the page that shows the posting. That page is `/jobs?job=<slug>`, and the slug is the site's own (for example `senior-python-ai-engineer-proxify-1925596` for the title "Senior AI Engineer"), so it cannot be derived from the title and company. One request per run to the site's own search endpoint (`/jobsapi/_search`, which its pages use; not a documented feed) asks for the slugs of all the feed's ids at once, within the board's rate limit. It reads only `id` and `slug`. If it fails, the run continues and the posting keeps the feed address. The owner approved using this endpoint.

### ADR-075 — freelancermap as a job board read from its public project pages

**Status:** approved by the owner on 2026-10-14; extends ADR-049 and ADR-070; follows research R-00176. **Reverses the exclusion of R-00176** (no API or feed exists).

**Context:** freelancermap is the main DACH market for freelance and contract IT projects, the owner's target (contract work with day rates). It has no API, feed or published reader terms. Its `robots.txt` blocks nothing and names a public sitemap of project pages. Its terms (`/term-and-conditions.html`, read 2026-10-14) do not mention automated access; §4(1)(a) asks users not to overload the service and §4(5) to use its information for their own purposes. The project pages embed each project as JSON for the site's own front end (`ProjectShow`): title, company, contract type (`contracting`, `permanent_position`, `employee_leasing`), remote share, place, skills, dates and description.

**Decision:**
1. freelancermap joins the fixed catalogue (`SourceType.FREELANCERMAP`, migration 0027) as a job board of ADR-049. It is the first job board read from HTML pages instead of an API; every other rule (filters, location scope, attribution, minimum interval of six hours, `409 too_soon`) applies unchanged.
2. The adapter reads the sitemap index, the project sitemaps, then only the project pages whose `lastmod` is within the age window, newest first, at most 120 pages a run, 15 a minute. `robots.txt` is honoured (a refusal stops the source). A run cut by the cap is `truncated` and never closes postings (`Page.capped`).
3. The embedded JSON is read directly: no AI and no CSS selectors. When several pages in a row carry no project data the run fails as `schema_changed` (ADR-070). Archived, disabled or inactive projects are skipped.
4. The contract type and remote share become the first lines of the description (`Contract type: Freelance`, `Remote: 100%`), so the extraction (ADR-073) quotes them as evidence. The day or hourly rate is not a field of the site (`budget` was empty in every sampled project); it is read from the text, so "Rate not stated" is expected for many offers.
5. Remote projects carry no list of eligible countries; their eligibility is unknown and the later judgement (the text, e.g. "Remote in EU") decides. Hybrid and on-site projects must be within the owner's radius, or have a place that could not be read.
6. Use stays personal: postings are stored and evaluated locally and are never exported or published. If the application is ever made available to anyone else, this board must be removed or its permission obtained (ODR-007).

### ADR-076 — Remotive as a job board

**Status:** approved by the owner on 2026-10-15 (asked to add it after the freelancermap check); the second-wave candidate of ADR-049.1, so it needs only a catalogue entry and an adapter; follows research R-00173 and the live notice of the API read on 2026-10-15.

**Context:** Remotive publishes a free public JSON feed (`/api/remote-jobs`, no key). Its notice asks to link back to the posting and name Remotive as the source, delays the data by 24 hours, asks for at most four requests a day and forbids submitting its jobs to third-party job sites (Jooble, Neuvoo, Google Jobs, LinkedIn Jobs). The free feed holds only a few dozen open postings. Each job states a category, a `job_type` (`full_time`, `contract`, `freelance`...), a free-text `candidate_required_location` and a free-text `salary`.

**Decision:**
1. Remotive joins the fixed catalogue (`SourceType.REMOTIVE`, migration 0028) as a job board of ADR-049; filters, location scope, attribution and `409 too_soon` apply unchanged.
2. Minimum interval between runs is six hours (the board's four-a-day limit) and two requests a minute; a run makes one request.
3. The board's `job_type` and `salary` are written into the description as `Job type stated by the board: ...` and `Salary stated by the board: ...`, so the extraction (ADR-073) quotes them as evidence. The salary is free text and is not parsed by the adapter.
4. The feed holds open postings only and is small, so the default window is 30 days, like the other small feeds (ADR-072.6, ADR-074.4).
5. Use stays personal: postings are stored and evaluated locally and are never submitted to any third-party site or published (ODR-007).

### ADR-077 — Faster extraction: parallel lanes, no idle loop, and no re-extraction of answered jobs

**Status:** requested by the owner on 2026-10-16 after measuring the worker (about 5 jobs a minute, the GPU idle for roughly a third of each cycle); implemented with it.

**Context:** `JOBS_RADAR_EXTRACTION_CONCURRENCY` existed but was never read, so jobs went to the model one at a time. The worker also paused `JOBS_RADAR_WORKER_POLL_SECONDS` after every 45-second batch even with a full queue. And a taxonomy upgrade (ADR-073) queued the open jobs again although they had an accepted answer, so most of the visible backlog was work already done.

**Decision:**
1. `ExtractionQueue.run_batch` runs `extraction_concurrency` lanes. The model call happens outside any transaction; the short database steps (claim, save, release) take turns on a lock. If the model is down, no lane claims another job and the batch ends as `stopped`. The default stays 1: more lanes help only when the model server answers in parallel (for Ollama, `OLLAMA_NUM_PARALLEL`).
2. `Worker.run_once` returns whether extraction ended its batch with a backlog; the loop then starts the next iteration at once. After an error, or with an empty queue, it still waits.
3. A job that already has a successful extraction of the current or an accepted prompt version (same provider and model) is never extracted again for a new prompt or taxonomy version: not queued (`enqueue_missing` ignores the taxonomy version for accepted answers) and, if a row was queued earlier, not claimed (`claim_next`). Such rows stay `pending` (finalised rows are immutable and deleting is reserved for the audited deletion path) and do not count in the pipeline status. A prompt that is meant to redo old answers must say so by leaving the old version out of `EXTRACTION_ACCEPTED_PROMPT_VERSIONS`. This narrows ADR-073: a new taxonomy term no longer re-extracts jobs by itself.

### ADR-078 — An MCP server so that agents can use Jobs Radar

**Status:** accepted by the owner on 2026-10-19 (the owner answered every open question, see the end of this entry); implemented as task T13 on 2026-10-19 (differences from the plan: `docs/design/mcp-server.md`, section 12). The implementation plan is `docs/design/mcp-server.md`.

**Context:** the owner wants coding and chat agents (for example Claude Code, or a local agent on Ollama) to read the inbox, explain a score, look at trends and, later, triage jobs by conversation. The Model Context Protocol (MCP) is the open standard those clients use to call tools. Jobs Radar already has a versioned REST API with validation, optimistic concurrency and error contracts; the interface is the missing piece, not the capability. The API has no authentication in V1 (ADR-009) and the MCP server inherits that: it adds no login and no new network exposure of its own.

**Decision:**
1. **A separate process, a thin client of the REST API.** The server is the package `jobs_radar.mcp_server`, started by the agent's client over **stdio** (`python -m jobs_radar.mcp_server`). It calls the running API (`/api/v1`) with `httpx` and never opens the database, never imports `services`, `repositories`, `db`, `adapters`, `worker` or `api`, and never writes anything by itself. Every rule (validation, `expected_version` conflicts, append-only revisions, inbox transitions) therefore stays in one place. An import-linter contract and a unit test enforce the boundary.
2. **stdio only; no network listener.** There is no HTTP/SSE transport in this decision. A client launches the process on the machine that runs it; nothing new listens on any port, so the "no authentication" rule of ADR-009 is not widened. A remote or multi-user transport (streamable HTTP) would need authentication and is a separate ADR. The server reaches the API at `JOBS_RADAR_MCP_API_URL` (default `http://127.0.0.1:8100`); it is the owner's choice to point it at a LAN API (ADR-065).
3. **SDK.** The official `mcp` package (MIT, `>=2.3,<3`; the server class is `mcp.server.MCPServer`), as an **optional extra** `mcp` of the backend, so the API and worker images do not carry it. The licence gate (no AGPL, no proprietary) and `pip-audit` cover its dependency tree.
4. **Phase 1 is read-only.** Tools, all annotated `readOnlyHint`: `get_status`, `list_inbox`, `get_job`, `get_daily_digest`, `list_search_intents`, `get_career_profile`, `list_sources`, `list_collection_runs`, `list_companies`, `get_company`, `get_trends`. They return compact, typed views (structured output), not the raw API payloads, with page-size and text-length limits so a reply never floods the agent's context.
5. **Phase 2 writes are part of the same delivery but off by default.** With `JOBS_RADAR_MCP_ALLOW_WRITES=true` the server also registers `inbox_action` (the existing owner actions: open, mark unread, shortlist, ignore, restore, archive, record application), `start_collection` (queue a run, as the button does) and `summarise_job` (the local model's append-only summary). Writes need `expected_version` from a prior read, so an agent cannot act on a stale view; each is reversible or append-only; each is marked `destructiveHint: false`, so clients can ask the owner to confirm. **Never exposed by any tool:** AI provider settings and credentials, source credentials, CV upload and document text, deletion, profile or intent edits, source add/enable, scoring weights. Those need their own ADR.
6. **Untrusted text.** Job descriptions and company texts come from third parties and can contain instructions aimed at an agent (prompt injection). Such text is returned only in fields named `untrusted_*`, wrapped in a fixed marker (`<untrusted-source-text>…</untrusted-source-text>`, with any marker found inside the text neutralised), truncated (`max_chars`, default 6,000), and every tool description says so. Phase 1 has no tool that could act on it; in phase 2 the allow-list in point 5 and `expected_version` bound the damage, and the owner's client confirmation is the last guard.
7. **Privacy of the data itself (owner decision: expose everything).** The tools return the profile and the intents in full, including employers, education, free-text notes and pay expectations; there is no "sensitive" switch. The agent's client may be a cloud model, and whatever a tool returns then leaves the machine. ADR-046 ("job analysis is local only") governs what Jobs Radar itself sends, not what the owner chooses to show their own agent, so the README and the operations guide state this plainly, for cloud agents and for local ones (Ollama or any local model behind an MCP-capable client). The protection is the master switch of point 10: the server does not start unless the owner turned it on.
8. **Errors and logging.** API errors (`{error:{code,message,details,request_id}}`) become MCP tool errors with the same code and message; an unreachable API says so and how to start it. Logs go to **stderr only** (stdout carries the protocol); no tool argument, job text or profile fact is logged, only the tool name, status, duration and `request_id`.
9. **The HTTP client is not the adapters' guarded client.** ADR-035's `GuardedHttpClient` blocks private addresses on purpose, and this client talks to the owner's own API on loopback or LAN. A small dedicated client is used instead: one configured base URL, no redirects, bounded timeouts and body size, and a fixed allow-list of method + path templates (a test compares it with `backend/openapi.json`, so API drift fails a test).
10. **Master switch in `.env`; fail closed.** The server starts only if `JOBS_RADAR_MCP_ENABLED` is `true` in the untracked `.env` (or in the process environment, which wins). If it is `false` or absent the process writes one line to stderr and exits with a non-zero status **before registering any tool or opening any connection**, so no agent can use it. Writes need a second, independent switch, `JOBS_RADAR_MCP_ALLOW_WRITES` (default `false`). The server holds no credential. It reads from `.env` only the keys that start with `JOBS_RADAR_MCP_` plus `JOBS_RADAR_API_PORT` (to find the API); every other key, including the encryption key and the database password, is never parsed into memory, logged or passed on. The file is `JOBS_RADAR_ENV_FILE` if set (as in the launcher) or the repository's `.env`. Settings: `JOBS_RADAR_MCP_ENABLED`, `JOBS_RADAR_MCP_ALLOW_WRITES`, `JOBS_RADAR_MCP_API_URL` (default `http://127.0.0.1:` + the API port), `JOBS_RADAR_MCP_TIMEOUT_SECONDS`; they are added to `.env.example` as `false` / defaults. `make mcp-config` prints the client snippet with absolute paths and no secrets; the project-level `.mcp.json` is git-ignored.

**Why:** an MCP server is the cheapest way to give the owner a conversational interface and automation hooks without building UI, and stdio over a thin client keeps the security model unchanged: same API, same rules, no new listener. Read-only first lets the owner see the value and the privacy cost before any agent may change state.

**Consequences:** new package `backend/src/jobs_radar/mcp_server/`; optional dependency `mcp`; import-linter contract; Make targets `mcp-config`, `test-mcp`; `.env.example` and the configuration reference gain the `JOBS_RADAR_MCP_*` variables; `make config-check` reports whether the server is enabled; the commit scope `mcp` is added to the contributing rules; `docs/operations/mcp-server.md`; README security and documentation sections; **no migration, no API change**. Tools are a public contract: a snapshot test lists them, so adding or changing one is a visible diff. Costs: one more contract to keep in step with the API (mitigated by the OpenAPI path test); the SDK's dependency tree to audit.

**Owner answers (2026-10-19):** expose the profile and intents in full; implement the write tools in the same round, behind their own switch; both cloud and local agents are intended clients; commit scope `mcp`. `JOBS_RADAR_MCP_ALLOW_WRITES` stays off by default even when the server is enabled (confirmed); the owner's local `.env` may enable it.

### ADR-079 — Install from published container images (release compose, generated secrets, one-command demo)

**Status:** proposed on 2026-10-20; the owner approved the direction (images public on GHCR, workflow in the new public repository `innovation-ways/iw-jobs-radar`, Ollama out of scope). Implementation follows this entry.

**Context:** installing Jobs Radar needs Docker, `uv`, Node and pnpm, a `.env` made by a bash script, and a build from source. That is fine for development and too much for someone who only wants to use the tool. The development compose also uses `network_mode: host` (so containers reach a loopback-only Ollama and the published database port), which is Linux-specific and does not behave the same on Docker Desktop (Windows, macOS). The frontend runs under Vite outside Docker.

**Decision:**
1. **Published images.** A workflow in the public repository builds and pushes, for each release created by release-please, two images to GHCR: `ghcr.io/innovation-ways/iw-jobs-radar-backend` (one image for the API and the worker; only the command differs) and `…-frontend` (static build served by nginx). Both are multi-arch (`linux/amd64`, `linux/arm64`), tagged with the exact version (and `latest`), and the packages are public. The build runs inside the release-please workflow (gated on its `release_created` output), because a tag created with `GITHUB_TOKEN` does not trigger other workflows. Third-party actions stay pinned by commit SHA. Images carry no secrets and no data.
2. **A user compose, separate from the development one.** `docker-compose.release.yml` uses `image:` only (no `build:`), a normal bridge network, the API reaching PostgreSQL as `db:5432`. The development `docker-compose.yml`, `docker-compose.dev.yml` and `jobs-radar.sh` are not changed. Versions are pinned through a single variable (`JOBS_RADAR_VERSION`), upgrades are `pull` + `up` (migrations run at API start, as today).
3. **Same origin, one published port.** The frontend container (nginx) serves the UI and proxies `/api`, `/healthz` and `/readyz` to the API, so there is no CORS. Only the frontend is published, on `127.0.0.1` (default port 5180, changeable). The database and the API are not published. V1 still has no authentication (ADR-009); binding to the LAN stays an explicit owner edit, as today.
4. **Secrets without a script.** An entrypoint of the backend image creates the credential key (ADR-033) and the database password on first start and stores them in a named volume (`jobs-radar-secrets`, file mode 0600); later starts reuse them. Values already present in the environment win (so the development flow is unchanged). The database container reads its password from the same volume. The README states that the key must be backed up: without it stored credentials cannot be recovered; a documented command prints it for the owner to save. The key is never logged.
5. **Demo in one command.** `docker-compose.demo.yml` is complete and self-contained (its own database, its own volumes, its own ports): one service runs `demo_seed`, another `idle_worker`, then the API and the frontend. The real worker never runs against it and it never touches the owner's data (ADR-046 / demo rules). The demo shows only fictional data.
6. **Ollama is out of scope.** The default stays No AI (ADR-046). Where a local model runs, and how a container reaches it, is the user's own environment choice; the documentation only says that `JOBS_RADAR_OLLAMA_URL` and `JOBS_RADAR_ALLOW_LOCAL_PROVIDERS` point Jobs Radar at it, and that a model server listening beyond loopback is exposed to that network. The release compose adds `host.docker.internal` for Linux and nothing else.
7. **README.** "Quick start" becomes the demo first, then the release compose; the `uv`/`pnpm` flow moves to a "Development" section.

**Why:** published images turn an hour of toolchain setup into `docker compose up`, work the same on Linux, macOS and Windows (bridge networking, no bash), and keep the security model unchanged: no new authentication surface, one loopback port, secrets generated locally and never in an image.

**Consequences:** new files `frontend/Dockerfile`, `frontend/nginx.conf`, a backend entrypoint, `docker-compose.release.yml`, `docker-compose.demo.yml`, a release image workflow and an install guide (`docs/operations/install.md`); README restructure; images become permanent public artefacts (a pushed tag is not recalled, so a bad release is fixed by a new one). Costs: a second compose to keep in step with the first (a unit test compares service names and environment keys); the user-facing test on a clean Linux VM and on Windows with Docker Desktop cannot be done by the agent and is part of the owner's acceptance. **No migration, no API change.**

### ADR-080 — Domain packs: the job domain becomes data, not code

**Status:** approved by the owner on 2026-10-20 after a design discussion; implemented in phases (the vocabulary editor and merge, then packs, then the pre-filter and the skills and requirements work). Each phase is recorded in the plan. The plan and the characterisation tests are in `docs/design/domain-packs.md`.

**Context:** the project is about to be shared as open source. Today it only fits a software or data professional. The controlled vocabulary (`role_family`, `sector`, …) was seeded by Alembic migrations from frozen Python constants (`domain/taxonomy_seed.py`, `taxonomy_additions.py`, `taxonomy_v3.py`) that are also imported at run time (`schemas/intent.py`, `demo/persona.py`) and by the frontend (`features/intent/defaults.ts`, `validate.ts`). The job-board pre-filter is five fixed regular expressions plus a fixed noise list (`domain/job_board_rules.py`). The extraction prompt mentions technology. Skills are technologies, methods and domain knowledge (`SkillKind`). Nothing models licences, shifts or travel. The matching engine, the stance model, the inbox, duplicates, immutable history and the worker are already domain-independent: the engine compares keys and stances only.

**Decision:**
1. **A domain pack is a versioned data file in the repository** (`backend/src/jobs_radar/packs/<pack_key>.json`, validated by a Pydantic schema with `schema_version`). It carries: role families and sectors (key, English label), pre-filter areas (key, label, whole-word keywords and phrases) and noise terms, credential terms, suggested default stances and suggested weights for a new Search Intent. Packs are English only (owner decision). Pack files are package data inside the backend image, so the published GHCR images (ADR-079) carry them; nothing is read from the repository at run time.
2. **Initial packs (ten, plus an empty "Custom"):** Software, data and IT (exactly today's taxonomy); Construction and skilled trades; Installation, maintenance and repair; Manufacturing and production; Logistics, transport and warehousing; Healthcare and social care; Retail, sales and customer service; Hospitality, food and tourism; Office, finance, legal and HR; Education and public services. They are written by the project (the ISCO-08 major groups are only a structural guide; no text from ISCO or ESCO is copied, and their licences are not relied on). The shipped packs must be complete enough that a user never has to add a term to start (owner decision); editing is for refining.
3. **Several packs may be active at once** (additive). Keys are unique per `(kind, term_key)` as today; generic kinds (seniority, work arrangement, engagement, employer type, benefit) stay global and are not pack data. Activating a pack is an owner action in a setup assistant and in settings.
4. **The database is the only source at run time.** A loader applies packs idempotently at start-up (migration or start-up step, not only on first install), so an installation upgraded from an older image receives new packs. Each term records its origin (`seed`/pack, `user`, `ai_proposal_accepted`; the existing `TermOrigin`) and the pack key. Applying a newer pack adds new terms; it never overwrites a label or state the owner changed, never deletes (a term removed from a pack is deactivated), and bumps `taxonomy_version` only when something changed. Term keys are immutable once created; a term can be deactivated or replaced (`replaced_by`), never deleted (ADR-022), so stored profile revisions, intent revisions, extractions and evaluations stay valid.
5. **The taxonomy is editable by the owner** (API and screen): add a term, edit a label, deactivate, merge via `replaced_by`. Only the owner creates terms (no AI-proposed terms in this ADR). The Python seed modules become migration-only history; no run-time code imports them. Migrations that import them are not edited (existing rule).
6. **The extraction prompt is built from the database, and lists only the terms of the active packs** (plus the global kinds and `other`). This keeps the prompt small for a local 8B model and matches what the owner searches for. For the owner's data the generated prompt must be byte-identical to `extract-v4` until phase 6 deliberately changes it (guarded by a golden test). Following ADR-077, activating a pack or adding a term re-extracts nothing by itself; the setup shows an explicit "Re-extract open jobs" action that the owner confirms.
7. **The pre-filter becomes data.** Areas and noise live in the pack files (area key, label, keyword list); the rules of an owner are those of the packs switched on, read from the files, with no table (refined in phase 5: nothing about them is owner-edited yet). The code builds one compiled, escaped whole-word pattern per area from keywords; the owner never writes a regular expression (no invalid or catastrophic patterns). For the Software pack the result must classify a frozen corpus of titles exactly as today's regexes do. A board with no area selected behaves as before. This changes only the board pre-filter (ADR-049/051), not scoring.
8. **Skills become generic (phase 6a).** `SkillKind` gains `tool_equipment` and `credential` (licence or certification, for example a driving licence, a gas or electrical certification). Alias, equivalence and candidate logic is unchanged. The profile keeps its typed skills; credentials are skills of kind `credential` with an optional expiry-free "held" fact.
9. **New job attributes and rules (phase 6b), backward compatible by construction:** extraction gains required credentials (must/nice), `schedule` (day, night, rotating shifts, weekends, on call) and `travel` (none, occasional, frequent, own vehicle needed). Stances (Preferred/Acceptable/Rejected) apply to `schedule` and `travel` like `work_arrangement`. Two dimensions, `schedule_travel`-style (final keys decided in the design) and the existing `qualifications` (now measuring credential coverage), enter with **weight 0 in every existing intent**, so no existing score changes; packs suggest weights for new intents. A gate **G12 "requires a credential I do not hold"** exists and is **off by default** (like G7 for languages). The policy version becomes `matching-v1.9`; evaluations of earlier versions are kept and a rescore creates new ones (existing rule). The commute radius already exists (`radius_km`, G2); the setup stops assuming remote work first by taking arrangement defaults from the pack.
10. **One re-extraction, agreed in advance.** The prompt changes once (phase 6b, `extract-v5`) to add credentials, schedule and travel. The old versions are left out of `EXTRACTION_ACCEPTED_PROMPT_VERSIONS` only if the owner chooses to re-extract; the owner decides when, because it costs local-model time. Until then existing answers stay valid and the new dimensions read as `unknown`.
11. **A setup assistant (phase 6c):** choose packs, then profile and credentials, then a Search Intent prefilled from the pack. Existing users are not forced through it: a migration marks the owner's installation as "Software, data and IT" active, with every term, stance and weight they have today.
12. **Out of scope, recorded on purpose:** job sources for non-technical work. The catalogue (Arbeitnow, Jobicy, Himalayas, ITJobs.pt, We Work Remotely, …) and the ATS adapters serve technology and remote work. Without general sources a tradesperson will find few postings even with a perfect taxonomy; "Follow a company" (ADR-070) is the only fit today. General sources each need their own permission and terms review and are the subject of a separate ADR (ODR-008). Also out of scope: translation or non-English labels and prompts, AI-proposed terms, currency conversion, commute time (the radius stays straight-line), physical-demand or health requirements.

**Why:** the engine is already generic, so the work is moving vocabulary, defaults and the pre-filter out of code and migrations and into data that the owner and the community can extend. Packs give a new user a complete starting point, additive packs fit people who search in two fields, and listing only active terms keeps small local models accurate. Keeping keys immutable and every new rule neutral for existing intents (weight 0, gate off, same prompt text) is how the current user loses nothing.

**Consequences:** new tables for pack activation, taxonomy term state and pre-filter areas (mutable configuration, with `updated_at`; taxonomy remains versioned); new API for taxonomy, packs and areas (`make api-client`); `schemas/intent.py` and the frontend stop importing seed constants; the demo persona reads the Software pack; `matching-v1.9`; prompt `extract-v5` in phase 6b; pack files in the image (a test resolves them as package data); documentation (doc 13 sections 2.1 and 2.2 are updated when each phase lands). Costs: more configuration surface to explain; ten packs to write and review; one deliberate re-extraction. **Migrations are two-step (add, move data, only then stop reading the old source), and `make backup` plus `make restore-drill` run before the first one.**

**Owner answers (2026-10-20):** all ten packs, several active at once, extraction prompt limited to active packs, one agreed re-extraction in phase 6, sources for non-technical work out of scope, English only, only the owner creates terms and the seed is enough to start, packs are repository files loaded into the database (images on GHCR carry them), work on `main` with no push until everything is confirmed.

## Open decisions — do not assume

| ID | Decision required | Options / trigger |
|---|---|---|
| ODR-006 | Default LLM provider/model recommendations | not decided; V1 default is No AI. Local Ollama is available on the development machine; choose suggested defaults after adapter validation (Increment on AI) |
| ODR-008 | Job sources for non-technical work (ADR-080, point 12) | not decided; each general source needs permission and a terms review; separate ADR before any adapter |
| ODR-007 | Legal/licence review for release | Released: the repository is licensed under Apache-2.0 (`LICENSE`, `NOTICE`). The terms of the data sources are in `docs/legal/data-sources.md`. We Work Remotely (ADR-072) and freelancermap (ADR-075) are for personal, local use only: their postings are never exported or published, and anyone who runs the application is responsible for the terms of the boards they enable. |

## Change rule

An implementation agent may clarify internal naming or make a low-risk technical choice that does not change these decisions. Any decision that changes data residency, user privacy, scoring semantics, collection sources, external exposure, or V1 scope must be added here as a proposed ADR and reviewed before implementation.
