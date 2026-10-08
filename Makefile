# Jobs Radar — developer entry points. Each target delegates to the backend or frontend tooling.
# Run `make help` for the list. Quality gates are described in CLAUDE.md.

BACKEND := backend
FRONTEND := frontend
GITLEAKS_IMAGE := ghcr.io/gitleaks/gitleaks:v8.30.1

.DEFAULT_GOAL := help
.PHONY: help install test test-unit test-integration coverage lint format format-check typecheck \
        arch-check security security-sast license-check docs-check secret-scan quality \
        docs-schema openapi fe-install fe-lint fe-format-check fe-typecheck fe-license-check test-frontend \
        fe-coverage test-e2e api-client quality-frontend check

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

install: ## Install backend and frontend dependencies
	cd $(BACKEND) && uv sync
	$(MAKE) fe-install

test: ## Run all backend tests (unit + integration; needs Docker)
	cd $(BACKEND) && uv run pytest tests/unit tests/integration -q

test-unit: ## Run backend unit tests (no Docker)
	cd $(BACKEND) && uv run pytest tests/unit -q

test-integration: ## Run backend integration tests (PostgreSQL testcontainer)
	cd $(BACKEND) && uv run pytest tests/integration -q

coverage: ## Run tests with coverage; fails below 80%
	cd $(BACKEND) && uv run pytest tests/unit tests/integration -q --cov --cov-report=term-missing

lint: ## Ruff lint
	cd $(BACKEND) && uv run ruff check .

format: ## Ruff format (rewrites files)
	cd $(BACKEND) && uv run ruff format .

format-check: ## Ruff format check (no changes)
	cd $(BACKEND) && uv run ruff format --check .

typecheck: ## mypy (strict)
	cd $(BACKEND) && uv run mypy

arch-check: ## import-linter architecture contracts
	cd $(BACKEND) && uv run lint-imports

security: ## bandit (fails on any finding of medium or higher severity)
	cd $(BACKEND) && uv run bandit -q -r src -ll

security-sast: ## semgrep SAST (needs network for the rule packs)
	cd $(BACKEND) && uvx semgrep --config p/python --config p/security-audit --metrics off --error --quiet src

license-check: ## No AGPL/SSPL/proprietary runtime dependency
	cd $(BACKEND) && uv run python -m jobs_radar.tools.check_licenses

docs-check: ## Every table and column has a comment
	cd $(BACKEND) && uv run python -m jobs_radar.tools.check_column_docs

docs-schema: ## Regenerate docs/database/schema.md from the ORM models
	cd $(BACKEND) && uv run python -m jobs_radar.tools.generate_schema_docs

# Scans the git history and the staged changes, i.e. everything that could be committed. The local,
# git-ignored .env (which legitimately holds secrets) is deliberately not scanned.
GITLEAKS_RUN := docker run --rm -v "$(CURDIR):/repo:ro" \
	-e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/repo $(GITLEAKS_IMAGE)

secret-scan: ## gitleaks over git history and staged changes (needs Docker)
	$(GITLEAKS_RUN) git /repo --no-banner --redact --exit-code 1
	$(GITLEAKS_RUN) git /repo --staged --no-banner --redact --exit-code 1

quality: lint format-check typecheck arch-check security license-check docs-check ## All fast quality gates (backend)
	@echo "Backend quality gates passed."

# --- frontend (pnpm via corepack; see CLAUDE.md) ---
PNPM := PATH="$$HOME/.local/bin:$$PATH" pnpm --dir $(FRONTEND)

fe-install: ## Install frontend dependencies (pnpm)
	$(PNPM) install --frozen-lockfile

fe-lint: ## ESLint (zero warnings)
	$(PNPM) lint

fe-format-check: ## Prettier check
	$(PNPM) format:check

fe-typecheck: ## TypeScript (strict)
	$(PNPM) typecheck

fe-license-check: ## No AGPL/SSPL production dependency (frontend)
	$(PNPM) license-check

test-frontend: ## Vitest component and unit tests
	$(PNPM) test

fe-coverage: ## Vitest with coverage
	$(PNPM) test:coverage

test-e2e: ## Playwright smoke tests against the running stack (./jobs-radar.sh --quick-start first)
	$(PNPM) e2e

api-client: openapi ## Regenerate the typed frontend API client from the backend OpenAPI document
	$(PNPM) api:generate

quality-frontend: fe-lint fe-format-check fe-typecheck fe-license-check ## All fast quality gates (frontend)
	@echo "Frontend quality gates passed."

check: quality quality-frontend test test-frontend ## Everything except SAST, secret scan and E2E
	@echo "All checks passed."

openapi: ## Export the OpenAPI document used to generate the frontend client
	cd $(BACKEND) && uv run python -m jobs_radar.tools.export_openapi
