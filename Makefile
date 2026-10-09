# Jobs Radar — developer commands. Run `make` (or `make help`) for the full, grouped list.
# Every target needs a "## description" and must be listed in .PHONY: a unit test enforces both,
# so the help can never fall out of date. Quality gates are described in CLAUDE.md.

BACKEND := backend
FRONTEND := frontend
GITLEAKS_IMAGE := ghcr.io/gitleaks/gitleaks:v8.30.1
LAUNCHER := ./jobs-radar.sh
PNPM := PATH="$$HOME/.local/bin:$$PATH" pnpm --dir $(FRONTEND)

.DEFAULT_GOAL := help
.PHONY: help install up down restart status health logs urls \
        test test-unit test-integration test-file test-k test-failed coverage coverage-html \
        test-frontend test-frontend-watch fe-coverage test-e2e \
        lint format format-check typecheck arch-check security license-check docs-check quality \
        fe-lint fe-format fe-format-check fe-typecheck fe-license-check quality-frontend check check-all \
        security-sast secret-scan docs-schema openapi api-client seed-dev-sources backup restore-drill backup-list restore fe-install clean

##@ Run the app

help: ## Show this list of commands
	@use_color=0; \
	if [ -z "$$NO_COLOR" ]; then if [ -n "$$FORCE_COLOR" ] || [ -t 1 ]; then use_color=1; fi; fi; \
	awk -v color=$$use_color ' \
	  BEGIN { b=y=g=d=n=""; \
	    if (color) { b="\033[1;34m"; y="\033[1;33m"; g="\033[0;32m"; d="\033[2m"; n="\033[0m" } \
	    print ""; print b "  Jobs Radar — developer commands" n; \
	    print d "  Usage: make <command>      Launcher with menu: ./jobs-radar.sh" n } \
	  /^##@/ { sub(/^##@ */, ""); print ""; print y "  " $$0 n; next } \
	  /^[a-zA-Z0-9_-]+:.*## / { t=$$0; sub(/:.*/, "", t); desc=$$0; sub(/^[^#]*## /, "", desc); \
	    printf "  %s%-26s%s %s\n", g, "make " t, n, desc } \
	  END { print "" }' $(MAKEFILE_LIST)

install: ## Install backend and frontend dependencies
	cd $(BACKEND) && uv sync
	$(MAKE) fe-install

up: ## Start everything (database, API, worker, frontend) and wait until healthy
	$(LAUNCHER) --quick-start

down: ## Stop everything
	$(LAUNCHER) --quick-stop

restart: ## Stop and start everything again
	$(LAUNCHER) --quick-stop
	$(LAUNCHER) --quick-start

status: ## Show what is running (containers and frontend)
	$(LAUNCHER) --status

health: ## Deep health check; fails if anything running is unhealthy
	$(LAUNCHER) --health

logs: ## Show a service's logs: make logs SVC=api (db | api | worker | frontend), LINES=100
	$(LAUNCHER) --logs $(or $(SVC),api) --lines $(or $(LINES),100)

urls: ## Print the addresses of the app, API docs and database
	$(LAUNCHER) --urls

##@ Backend tests

test: ## All backend tests: unit + integration (needs Docker)
	cd $(BACKEND) && uv run pytest tests/unit tests/integration -q

test-unit: ## Backend unit tests only (fast, no Docker)
	cd $(BACKEND) && uv run pytest tests/unit -q

test-integration: ## Backend integration tests (throw-away PostgreSQL container)
	cd $(BACKEND) && uv run pytest tests/integration -q

test-file: ## Run one backend test file: make test-file FILE=tests/unit/test_settings.py
	$(if $(FILE),,$(error FILE is required, e.g. make test-file FILE=tests/unit/test_settings.py))
	cd $(BACKEND) && uv run pytest $(FILE) -v

test-k: ## Run backend tests whose name matches a word: make test-k K=inbox
	$(if $(K),,$(error K is required, e.g. make test-k K=inbox))
	cd $(BACKEND) && uv run pytest tests -k "$(K)" -v

test-failed: ## Re-run only the backend tests that failed last time
	cd $(BACKEND) && uv run pytest tests --lf -v

coverage: ## Backend tests with coverage; fails below 80%
	cd $(BACKEND) && uv run pytest tests/unit tests/integration -q --cov --cov-report=term-missing

coverage-html: ## Backend coverage as a browsable report in backend/htmlcov/index.html
	cd $(BACKEND) && uv run pytest tests/unit tests/integration -q --cov --cov-report=html
	@echo "Open backend/htmlcov/index.html"

##@ Frontend tests

test-frontend: ## Frontend unit and component tests (Vitest)
	$(PNPM) test

test-frontend-watch: ## Frontend tests that re-run when you save a file
	$(PNPM) exec vitest

fe-coverage: ## Frontend tests with a coverage summary
	$(PNPM) test:coverage

##@ End-to-end (real browser; needs the app running: make up)

test-e2e: ## Browser smoke tests against the running app (Playwright)
	$(PNPM) e2e

##@ Quality gates

lint: ## Backend lint (ruff)
	cd $(BACKEND) && uv run ruff check .

format: ## Backend: rewrite files to the standard format (ruff)
	cd $(BACKEND) && uv run ruff format .

format-check: ## Backend: check formatting without changing files
	cd $(BACKEND) && uv run ruff format --check .

typecheck: ## Backend type check (mypy strict)
	cd $(BACKEND) && uv run mypy

arch-check: ## Backend architecture rules (import-linter)
	cd $(BACKEND) && uv run lint-imports

security: ## Backend security lint (bandit, medium severity and above)
	cd $(BACKEND) && uv run bandit -q -r src -ll

license-check: ## Backend: no AGPL, SSPL or proprietary runtime dependency
	cd $(BACKEND) && uv run python -m jobs_radar.tools.check_licenses

docs-check: ## Every database table and column has a comment
	cd $(BACKEND) && uv run python -m jobs_radar.tools.check_column_docs

quality: lint format-check typecheck arch-check security license-check docs-check ## All fast backend quality gates
	@echo "Backend quality gates passed."

fe-lint: ## Frontend lint (ESLint, zero warnings)
	$(PNPM) lint

fe-format: ## Frontend: rewrite files to the standard format (Prettier)
	$(PNPM) format

fe-format-check: ## Frontend: check formatting without changing files
	$(PNPM) format:check

fe-typecheck: ## Frontend type check (TypeScript strict)
	$(PNPM) typecheck

fe-license-check: ## Frontend: no AGPL or SSPL production dependency
	$(PNPM) license-check

quality-frontend: fe-lint fe-format-check fe-typecheck fe-license-check ## All fast frontend quality gates
	@echo "Frontend quality gates passed."

check: quality quality-frontend test test-frontend ## Everything fast: quality gates + all tests (needs Docker)
	@echo "All checks passed."

check-all: check security-sast secret-scan ## check + security scan + secret scan (needs network and Docker)
	@echo "Everything passed (run 'make test-e2e' too when the app is running)."

##@ Security (needs network / Docker)

security-sast: ## Static security analysis (semgrep; downloads rule packs)
	cd $(BACKEND) && uvx semgrep --config p/python --config p/security-audit --metrics off --error --quiet src

# Scans the git history and the staged changes, i.e. everything that could be committed. The local,
# git-ignored .env (which legitimately holds secrets) is deliberately not scanned.
GITLEAKS_RUN := docker run --rm -v "$(CURDIR):/repo:ro" \
	-e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/repo $(GITLEAKS_IMAGE)

secret-scan: ## Look for committed secrets in history and staged changes (gitleaks, Docker)
	$(GITLEAKS_RUN) git /repo --no-banner --redact --exit-code 1
	$(GITLEAKS_RUN) git /repo --staged --no-banner --redact --exit-code 1

##@ Data & contracts

docs-schema: ## Regenerate docs/database/schema.md (database data dictionary)
	cd $(BACKEND) && uv run python -m jobs_radar.tools.generate_schema_docs

openapi: ## Export the API description to backend/openapi.json
	cd $(BACKEND) && uv run python -m jobs_radar.tools.export_openapi

api-client: openapi ## Regenerate the typed frontend API client after an API change
	$(PNPM) api:generate

seed-dev-sources: ## Add the 14 research boards as DISABLED sources to the dev database (no network)
	cd $(BACKEND) && uv run python -m jobs_radar.tools.seed_dev_sources

##@ Backup and restore

backup: ## Back up the database and the credential key into backups/ (git-ignored)
	cd $(BACKEND) && uv run python -m jobs_radar.tools.backup backup

restore-drill: ## Prove the latest dump: restore into a scratch database and compare every table
	cd $(BACKEND) && uv run python -m jobs_radar.tools.backup drill

backup-list: ## List the backups and their migration version
	cd $(BACKEND) && uv run python -m jobs_radar.tools.backup list

restore: ## Replace the database with a backup: make restore BACKUP=backups/backup-... CONFIRM=yes
	@test -n "$(BACKUP)" || { echo "usage: make restore BACKUP=backups/backup-YYYYMMDD-HHMMSS CONFIRM=yes"; exit 2; }
	@test "$(CONFIRM)" = "yes" || { echo "This replaces the current database. Add CONFIRM=yes to proceed."; exit 2; }
	cd $(BACKEND) && uv run python -m jobs_radar.tools.backup restore ../$(BACKUP) --yes

##@ Housekeeping

fe-install: ## Install frontend dependencies only (pnpm)
	$(PNPM) install --frozen-lockfile

clean: ## Delete caches and generated reports (never source files or data)
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache $(BACKEND)/htmlcov \
	       $(BACKEND)/.coverage $(FRONTEND)/dist $(FRONTEND)/coverage $(FRONTEND)/test-results \
	       $(FRONTEND)/playwright-report
	@echo "Caches and reports removed."
