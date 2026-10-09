"""HTTP routes. ``v1_router`` collects every versioned endpoint under ``/api/v1``."""

from fastapi import APIRouter

from jobs_radar.api.routes import (
    ai_settings,
    companies,
    company_dossier,
    digests,
    documents,
    evaluations,
    inbox,
    intents,
    locations,
    pipeline,
    profiles,
    proposals,
    schedule,
    sources,
    trends,
)

v1_router = APIRouter(prefix="/api/v1")
# Included once at import time so building several applications (tests) never duplicates routes.
v1_router.include_router(sources.router)
v1_router.include_router(profiles.router)
v1_router.include_router(intents.router)
v1_router.include_router(locations.router)
v1_router.include_router(evaluations.router)
v1_router.include_router(inbox.router)
v1_router.include_router(schedule.router)
v1_router.include_router(digests.router)
v1_router.include_router(ai_settings.router)
v1_router.include_router(documents.router)
v1_router.include_router(proposals.router)
v1_router.include_router(companies.router)
v1_router.include_router(company_dossier.router)
v1_router.include_router(trends.router)
v1_router.include_router(pipeline.router)
