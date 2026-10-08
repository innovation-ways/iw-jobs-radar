"""HTTP routes. ``v1_router`` collects every versioned endpoint under ``/api/v1``."""

from fastapi import APIRouter

v1_router = APIRouter(prefix="/api/v1")
