# Backend image shared by the API and the worker (ADR-038).
# Build arg INSTALL_DEV=true adds development dependencies (used by docker-compose.dev.yml).
FROM python:3.14-slim

ARG INSTALL_DEV=false
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

WORKDIR /app

# Dependencies first so this layer is cached until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN if [ "$INSTALL_DEV" = "true" ]; then uv sync --frozen --no-install-project; \
    else uv sync --frozen --no-dev --no-install-project; fi

COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN if [ "$INSTALL_DEV" = "true" ]; then uv sync --frozen; else uv sync --frozen --no-dev; fi

# Run as an unprivileged user.
RUN useradd --system --create-home --uid 10001 jobsradar
USER jobsradar

EXPOSE 8000
CMD ["uvicorn", "jobs_radar.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
