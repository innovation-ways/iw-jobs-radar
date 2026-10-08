"""FastAPI dependencies that build services from application state."""

from collections.abc import AsyncIterator, Mapping
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.sources.base import JobSourceAdapter
from jobs_radar.core.settings import Settings
from jobs_radar.domain.enums import SourceType
from jobs_radar.services.collection import CollectionService
from jobs_radar.services.dedup import DedupService
from jobs_radar.services.evaluation import EvaluationService
from jobs_radar.services.inbox import InboxService
from jobs_radar.services.intents import IntentService
from jobs_radar.services.profiles import ProfileService
from jobs_radar.services.readiness import ReadinessService
from jobs_radar.services.schedule import ScheduleService
from jobs_radar.services.sources import SourceService
from jobs_radar.services.taxonomy import TaxonomyService


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


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a database session for one request; the route commits what it wants to keep."""
    async with request.app.state.session_factory() as session:
        yield session


def get_adapters(request: Request) -> Mapping[SourceType, JobSourceAdapter]:
    """Return the job source adapters registered at start-up."""
    adapters: Mapping[SourceType, JobSourceAdapter] = request.app.state.adapters
    return adapters


def get_source_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    adapters: Annotated[Mapping[SourceType, JobSourceAdapter], Depends(get_adapters)],
) -> SourceService:
    """Build the source service on the request's session."""
    return SourceService(session, adapters)


def get_collection_service(request: Request) -> CollectionService:
    """Build the collection service; it opens its own short sessions per step."""
    return CollectionService(request.app.state.session_factory, get_adapters(request))


def get_profile_service(session: Annotated[AsyncSession, Depends(get_session)]) -> ProfileService:
    """Build the profile service on the request's session."""
    return ProfileService(session)


def get_intent_service(session: Annotated[AsyncSession, Depends(get_session)]) -> IntentService:
    """Build the intent service on the request's session."""
    return IntentService(session)


def get_taxonomy_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TaxonomyService:
    """Build the taxonomy service on the request's session."""
    return TaxonomyService(session)


def get_evaluation_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvaluationService:
    """Build the evaluation service; the API never calls an AI provider (the worker does)."""
    return EvaluationService(session, provider=None)


def get_inbox_service(session: Annotated[AsyncSession, Depends(get_session)]) -> InboxService:
    """Build the inbox service on the request's session."""
    return InboxService(session)


def get_dedup_service(session: Annotated[AsyncSession, Depends(get_session)]) -> DedupService:
    """Build the dedup service; the API never calls an embedding model (the worker does)."""
    return DedupService(session)


def get_schedule_service(session: Annotated[AsyncSession, Depends(get_session)]) -> ScheduleService:
    """Build the schedule service on the request's session."""
    return ScheduleService(session)
