"""Liveness and readiness endpoints. They expose no personal data or secrets (TR-5.5)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from jobs_radar.api.deps import get_readiness_service
from jobs_radar.services.readiness import ReadinessService

router = APIRouter(tags=["health"])


@router.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    """Describe the service so that opening the API address in a browser is not a bare 404."""
    return {
        "name": "Jobs Radar API",
        "docs": "/docs",
        "health": "/healthz",
        "ready": "/readyz",
        "note": "This is the API. The web interface runs on the frontend port.",
    }


class LivenessResponse(BaseModel):
    """Body of ``/healthz``."""

    status: str


class ReadinessResponse(BaseModel):
    """Body of ``/readyz``."""

    status: str
    components: dict[str, str]


@router.get("/healthz", response_model=LivenessResponse)
async def healthz() -> LivenessResponse:
    """Process liveness: answers without touching the database."""
    return LivenessResponse(status="ok")


@router.get(
    "/readyz", response_model=ReadinessResponse, responses={503: {"model": ReadinessResponse}}
)
async def readyz(
    service: Annotated[ReadinessService, Depends(get_readiness_service)],
) -> JSONResponse:
    """Dependency readiness: database reachable and worker heartbeat fresh."""
    report = await service.check()
    body = ReadinessResponse(
        status="ready" if report.ready else "unavailable",
        components={"database": report.database.value, "worker": report.worker.value},
    )
    return JSONResponse(body.model_dump(), status_code=200 if report.ready else 503)
