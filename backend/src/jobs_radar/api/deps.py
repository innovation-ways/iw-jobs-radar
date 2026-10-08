"""FastAPI dependencies that build services from application state."""

from fastapi import Request

from jobs_radar.core.settings import Settings
from jobs_radar.services.readiness import ReadinessService


def get_settings_dep(request: Request) -> Settings:
    """Return the settings the application was created with."""
    settings: Settings = request.app.state.settings
    return settings


def get_readiness_service(request: Request) -> ReadinessService:
    """Build the readiness service for the current request."""
    settings: Settings = request.app.state.settings
    return ReadinessService(
        request.app.state.session_factory, settings.worker_heartbeat_max_age_seconds
    )
