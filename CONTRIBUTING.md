# Contributing to Jobs Radar

Thank you for helping. Jobs Radar is a local-first, single-user job-market radar (see `README.md`).

## Ground rules

- Be kind: this project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- Everything in the repository is in **English**: code, comments, docstrings, identifiers, commit
  messages and documentation.
- Open an issue before a large change, so we can agree on the approach. Changes that touch privacy
  (what leaves the machine), scoring semantics, collection sources or external exposure need a
  discussion first.
- Test data is **synthetic only**: no real CVs, personal data, credentials or live job payloads in
  tests, fixtures or screenshots.

## Setup

Prerequisites: Docker, [`uv`](https://docs.astral.sh/uv/), Node 22 with pnpm through corepack.

```bash
make install        # backend and frontend dependencies
make help           # every command
make check          # quality gates and all tests (needs Docker for the PostgreSQL test container)
```

The tests never touch the network or a development database. `make check` is what CI runs; it must
pass before a pull request is merged.

## Code standards

- Tests first: write a failing test, make it pass, then refactor.
- Python: type hints (mypy strict), ruff, a module docstring in every file and a docstring on every
  class and public function. The layers (`api` → `services` → `repositories` → `db`) and the pure
  matching module are enforced by import-linter (`make quality`).
- TypeScript: strict mode, JSDoc on exported components and functions.
- Every database column has a `comment=`; every schema change has an Alembic migration.
- Changing the API: run `make api-client` and commit `backend/openapi.json` and
  `frontend/src/api/schema.d.ts`.

## Commits and pull requests

- Conventional Commits: `<type>(<scope>): <description>` with types `feat|fix|docs|refactor|test|chore`
  and scopes `api|db|worker|frontend|ci|config`.
- Keep pull requests focused and describe what changed and why.

## Developer Certificate of Origin (DCO)

By contributing you certify that you wrote the change or have the right to submit it under the
project's Apache-2.0 licence (the text of the [DCO 1.1](https://developercertificate.org/)). Sign off
every commit:

```bash
git commit -s -m "fix(api): ..."
```

This adds a `Signed-off-by: Your Name <you@example.com>` line.
