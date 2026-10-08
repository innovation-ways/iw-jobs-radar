"""HTTP routes. ``v1_router`` collects every versioned endpoint under ``/api/v1``."""

from fastapi import APIRouter

from jobs_radar.api.routes import intents, profiles, sources

v1_router = APIRouter(prefix="/api/v1")
# Included once at import time so building several applications (tests) never duplicates routes.
v1_router.include_router(sources.router)
v1_router.include_router(profiles.router)
v1_router.include_router(intents.router)
