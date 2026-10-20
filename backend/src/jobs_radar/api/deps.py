"""FastAPI dependencies that build services from application state."""

from collections.abc import AsyncIterator, Mapping
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.enrichment.registry import build_enrichment_adapters, build_website_reader
from jobs_radar.adapters.sources.base import JobSourceAdapter
from jobs_radar.adapters.sources.detector import CareersDetector
from jobs_radar.adapters.sources.page_config import PageConfigAdapter
from jobs_radar.core.errors import DependencyUnavailableError
from jobs_radar.core.http import build_http_client
from jobs_radar.core.settings import Settings
from jobs_radar.domain.enums import LOCAL_OWNER_ID, SourceType
from jobs_radar.repositories.companies import CompanyRepository
from jobs_radar.repositories.inbox import InboxQueries
from jobs_radar.repositories.sources import SourceRepository
from jobs_radar.services.ai_settings import AiSettingsService, build_credential_box
from jobs_radar.services.application_draft import ApplicationDraftService
from jobs_radar.services.collection import CollectionService
from jobs_radar.services.companies import CompanyService
from jobs_radar.services.company_analysis import CompanyAnalysisService, SiteReader
from jobs_radar.services.company_onboarding import CompanyOnboardingService
from jobs_radar.services.company_summary import CompanySummaryService
from jobs_radar.services.dedup import DedupService
from jobs_radar.services.direction_assess import DirectionAssessService
from jobs_radar.services.document_store import DocumentTextStore
from jobs_radar.services.documents import DocumentService
from jobs_radar.services.enrichment import EnrichmentAdapters, EnrichmentService
from jobs_radar.services.evaluation import EvaluationService
from jobs_radar.services.inbox import InboxService
from jobs_radar.services.integrations import IntegrationService
from jobs_radar.services.intents import IntentService
from jobs_radar.services.location_scope import LocationScopeService
from jobs_radar.services.packs import PackService
from jobs_radar.services.page_reader_proposal import PageReaderProposalService
from jobs_radar.services.pipeline import PipelineService
from jobs_radar.services.profile_data import ProfileDataService
from jobs_radar.services.profiles import ProfileService
from jobs_radar.services.proposal_review import ReviewService
from jobs_radar.services.proposals import ProposalService
from jobs_radar.services.readiness import ReadinessService, migration_head
from jobs_radar.services.schedule import ScheduleService
from jobs_radar.services.sources import SourceService
from jobs_radar.services.summary_assess import SummaryAssessService
from jobs_radar.services.taxonomy import TaxonomyService
from jobs_radar.services.trends import TrendService


def get_settings_dep(request: Request) -> Settings:
    """Return the settings the application was created with."""
    settings: Settings = request.app.state.settings
    return settings


def get_readiness_service(request: Request) -> ReadinessService:
    """Build the readiness service for the current request."""
    settings: Settings = request.app.state.settings
    return ReadinessService(
        request.app.state.session_factory,
        settings.worker_heartbeat_max_age_seconds,
        migration_head(),
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
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    adapters: Annotated[Mapping[SourceType, JobSourceAdapter], Depends(get_adapters)],
) -> SourceService:
    """Build the source service on the request's session (with the credential box, if any)."""
    return SourceService(session, adapters, box=build_credential_box(request.app.state.settings))


def get_careers_detector(request: Request) -> CareersDetector:
    """Return the careers-page detector, built once; tests may replace it on ``app.state``."""
    detector: CareersDetector | None = getattr(request.app.state, "careers_detector", None)
    if detector is None:
        detector = CareersDetector(build_http_client(), get_adapters(request))
        request.app.state.careers_detector = detector
    return detector


def get_company_onboarding_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    sources: Annotated[SourceService, Depends(get_source_service)],
    detector: Annotated[CareersDetector, Depends(get_careers_detector)],
) -> CompanyOnboardingService:
    """Build the follow-a-company use case on the request's session."""
    return CompanyOnboardingService(
        CompanyService(session),
        sources,
        CompanyRepository(session),
        SourceRepository(session),
        detector,
    )


def get_location_scope_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LocationScopeService:
    """Build the location scope service on the request's session."""
    return LocationScopeService(session)


def get_collection_service(request: Request) -> CollectionService:
    """Build the collection service; it opens its own short sessions per step."""
    return CollectionService(
        request.app.state.session_factory,
        get_adapters(request),
        box=build_credential_box(request.app.state.settings),
    )


def get_profile_service(session: Annotated[AsyncSession, Depends(get_session)]) -> ProfileService:
    """Build the profile service on the request's session."""
    return ProfileService(session)


def get_intent_service(session: Annotated[AsyncSession, Depends(get_session)]) -> IntentService:
    """Build the intent service on the request's session."""
    return IntentService(session)


def get_pack_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PackService:
    """Build the pack service on the request's session."""
    return PackService(session)


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


def get_pipeline_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> PipelineService:
    """Build the pipeline status service on the request's session."""
    settings: Settings = request.app.state.settings
    return PipelineService(session, settings.worker_heartbeat_max_age_seconds)


def get_inbox_service(session: Annotated[AsyncSession, Depends(get_session)]) -> InboxService:
    """Build the inbox service on the request's session."""
    return InboxService(session)


def get_dedup_service(session: Annotated[AsyncSession, Depends(get_session)]) -> DedupService:
    """Build the dedup service; the API never calls an embedding model (the worker does)."""
    return DedupService(session)


def get_schedule_service(session: Annotated[AsyncSession, Depends(get_session)]) -> ScheduleService:
    """Build the schedule service on the request's session."""
    return ScheduleService(session)


def get_ai_settings_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> AiSettingsService:
    """Build the AI settings service; tests may replace the provider builder and resolver."""
    state = request.app.state
    kwargs = {}
    if (resolver := getattr(state, "url_resolver", None)) is not None:
        kwargs["resolver"] = resolver
    return AiSettingsService(
        session,
        state.settings,
        box=build_credential_box(state.settings),
        provider_builder=getattr(state, "provider_builder", None),
        **kwargs,
    )


def get_document_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> DocumentService:
    """Build the document service on the request's session and the process-wide text store."""
    store: DocumentTextStore = request.app.state.document_texts
    return DocumentService(session, store)


def get_proposal_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    ai: Annotated[AiSettingsService, Depends(get_ai_settings_service)],
) -> ProposalService:
    """Build the proposal service with the AI settings and the in-memory CV text store."""
    state = request.app.state
    return ProposalService(session, state.settings, state.document_texts, ai)


def get_review_service(session: Annotated[AsyncSession, Depends(get_session)]) -> ReviewService:
    """Build the review service on the request's session."""
    return ReviewService(session)


def get_profile_data_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProfileDataService:
    """Build the export and deletion service on the request's session."""
    return ProfileDataService(session)


def get_company_service(session: Annotated[AsyncSession, Depends(get_session)]) -> CompanyService:
    """Build the company service on the request's session."""
    return CompanyService(session)


async def get_inbox_default_intent(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> int | None:
    """Return the owner's first enabled intent, used when a request names none."""
    return await InboxQueries(session).default_intent_id(LOCAL_OWNER_ID)


def get_integration_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> IntegrationService:
    """Build the integration-credential service (write-only tokens)."""
    return IntegrationService(session, box=build_credential_box(request.app.state.settings))


async def get_enrichment_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    integrations: Annotated[IntegrationService, Depends(get_integration_service)],
) -> EnrichmentService:
    """Build the enrichment service; tests may replace the adapters on the application state."""
    adapters = getattr(request.app.state, "enrichment_adapters", None)
    if adapters is None:
        token = await integrations.token(LOCAL_OWNER_ID, "github")
        wikidata, wikipedia, gleif, github = build_enrichment_adapters(token)
        adapters = EnrichmentAdapters(wikidata, wikipedia, gleif, github)
    return EnrichmentService(session, adapters)


def get_company_summary_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    ai: Annotated[AiSettingsService, Depends(get_ai_settings_service)],
) -> CompanySummaryService:
    """Build the AI company-summary service (local model only)."""
    return CompanySummaryService(session, ai)


def get_company_analysis_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    ai: Annotated[AiSettingsService, Depends(get_ai_settings_service)],
) -> CompanyAnalysisService:
    """Build the deep company analysis (local model); tests may replace the site reader."""
    reader: SiteReader | None = getattr(request.app.state, "site_reader", None)
    if reader is None:
        reader = build_website_reader()
    return CompanyAnalysisService(session, ai, reader=reader)


def get_trend_service(session: Annotated[AsyncSession, Depends(get_session)]) -> TrendService:
    """Build the trends service on the request's session."""
    return TrendService(session)


def get_direction_assess_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    ai: Annotated[AiSettingsService, Depends(get_ai_settings_service)],
) -> DirectionAssessService:
    """Build the service that assesses one job against the owner's career directions."""
    settings: Settings = request.app.state.settings
    return DirectionAssessService(session, ai, max_chars=settings.extraction_max_chars)


def get_summary_assess_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    ai: Annotated[AiSettingsService, Depends(get_ai_settings_service)],
) -> SummaryAssessService:
    """Build the service that writes the summary of one job with the local jobs model."""
    settings: Settings = request.app.state.settings
    return SummaryAssessService(session, ai, max_chars=settings.extraction_max_chars)


def get_application_draft_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    ai: Annotated[AiSettingsService, Depends(get_ai_settings_service)],
) -> ApplicationDraftService:
    """Build the service that writes pre-application drafts with the local jobs model."""
    settings: Settings = request.app.state.settings
    return ApplicationDraftService(session, ai, max_chars=settings.extraction_max_chars)


def get_page_reader_proposal_service(
    request: Request,
    ai: Annotated[AiSettingsService, Depends(get_ai_settings_service)],
) -> PageReaderProposalService:
    """Build the careers-page reader proposal (local model only, ADR-070)."""
    adapter = get_adapters(request).get(SourceType.PAGE_CONFIG)
    if not isinstance(adapter, PageConfigAdapter):
        msg = "Reading careers pages is not available in this build."
        raise DependencyUnavailableError(msg)
    return PageReaderProposalService(ai, adapter)
