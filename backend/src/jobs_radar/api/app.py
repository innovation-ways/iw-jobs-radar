"""Application factory: wires settings, logging, middleware, error handlers and routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from jobs_radar import __version__
from jobs_radar.adapters.sources.registry import build_source_adapters
from jobs_radar.api.middleware import RequestIdMiddleware
from jobs_radar.api.routes import health, v1_router
from jobs_radar.core.errors import AppError
from jobs_radar.core.logging import configure_logging, current_request_id
from jobs_radar.core.settings import Settings, get_settings
from jobs_radar.db.session import build_engine, build_session_factory
from jobs_radar.schemas.errors import ErrorBody, ErrorEnvelope
from jobs_radar.services.document_store import DocumentTextStore

_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


def _envelope(
    status: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    body = ErrorEnvelope(
        error=ErrorBody(
            code=code, message=message, details=details or {}, request_id=current_request_id()
        )
    )
    return JSONResponse(body.model_dump(), status_code=status)


async def _handle_app_error(_request: Request, exc: Exception) -> JSONResponse:
    error = cast(AppError, exc)  # registered for AppError only
    return _envelope(error.status_code, error.code, error.message, error.details)


async def _handle_http_error(_request: Request, exc: Exception) -> JSONResponse:
    error = cast(StarletteHTTPException, exc)  # registered for this type only
    code = _HTTP_CODES.get(error.status_code, "http_error")
    return _envelope(error.status_code, code, str(error.detail))


async def _handle_validation_error(_request: Request, exc: Exception) -> JSONResponse:
    error = cast(RequestValidationError, exc)  # registered for this type only
    # Only location, message and type are returned: never echo the submitted values (privacy).
    errors = [
        {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
        for item in error.errors()
    ]
    return _envelope(422, "validation_error", "Request validation failed.", {"errors": errors})


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application. ``settings`` defaults to the environment configuration."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(settings)
        app.state.engine = engine
        app.state.session_factory = build_session_factory(engine)
        app.state.adapters = build_source_adapters()
        # Extracted CV text lives here only, briefly and in memory (ADR-010).
        app.state.document_texts = DocumentTextStore()
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Jobs Radar API", version=__version__, lifespan=lifespan)
    app.state.settings = settings

    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health.router)
    app.include_router(v1_router)
    return app
