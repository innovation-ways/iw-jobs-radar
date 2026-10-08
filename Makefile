# Jobs Radar — developer entry points. Each target delegates to the backend or frontend tooling.
# Run `make help` for the list. Quality gates are described in CLAUDE.md.

BACKEND := backend
FRONTEND := frontend
GITLEAKS_IMAGE := ghcr.io/gitleaks/gitleaks:v8.30.1

.DEFAULT_GOAL := help
.PHONY: help install test test-unit test-integration coverage lint format format-check typecheck \
        arch-check security security-sast license-check docs-check secret-scan quality \
        openapi

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

install: ## Install backend dependencies (uv)
	cd $(BACKEND) && uv sync

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

secret-scan: ## gitleaks over the working tree (needs Docker)
	docker run --rm -v "$(CURDIR):/repo:ro" $(GITLEAKS_IMAGE) dir /repo --no-banner --redact --exit-code 1

quality: lint format-check typecheck arch-check security license-check docs-check ## All fast quality gates (backend)
	@echo "Quality gates passed."

openapi: ## Export the OpenAPI document used to generate the frontend client
	cd $(BACKEND) && uv run python -m jobs_radar.tools.export_openapi
