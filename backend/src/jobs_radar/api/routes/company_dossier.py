"""Company dossier endpoints (document 07)."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import (
    get_company_analysis_service,
    get_company_service,
    get_company_summary_service,
    get_enrichment_service,
    get_inbox_default_intent,
    get_session,
)
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.domain.matching.engine import band_of
from jobs_radar.schemas.company import CompanyWebsiteSet
from jobs_radar.schemas.company_dossier import (
    BoardRead,
    CandidateRead,
    CompanyDossierRead,
    FactRead,
    HiringWeekRead,
    OfferRead,
)
from jobs_radar.schemas.evaluation import FitBand
from jobs_radar.services.companies import CompanyService, Dossier
from jobs_radar.services.company_analysis import CompanyAnalysisService
from jobs_radar.services.company_summary import CompanySummaryService
from jobs_radar.services.enrichment import EnrichmentService

router = APIRouter(tags=["companies"])

Companies = Annotated[CompanyService, Depends(get_company_service)]
Enrichment = Annotated[EnrichmentService, Depends(get_enrichment_service)]
DefaultIntent = Annotated[int | None, Depends(get_inbox_default_intent)]
Session = Annotated[AsyncSession, Depends(get_session)]
_LABELS = {
    "source": "Source",
    "public_dataset": "Source",
    "ai_inference": "AI inference",
    "user": "You",
}


def dossier_read(dossier: Dossier, warnings: list[str] | None = None) -> CompanyDossierRead:
    """Map a dossier to its API model."""
    company = dossier.company
    return CompanyDossierRead(
        company_id=company.company_id,
        name=company.canonical_name,
        homepage_url=company.homepage_url,
        careers_url=company.careers_url,
        employer_type=company.employer_type,
        enriched_at=company.enriched_at,
        stale=dossier.stale,
        is_followed=dossier.is_followed,
        is_ignored=dossier.is_ignored,
        offers_truncated=dossier.offers_truncated,
        facts=[
            FactRead(
                fact_key=f.fact_key,
                value=f.value,
                origin=f.origin,
                label=_LABELS[f.origin],
                source_name=f.source_name,
                source_url=f.source_url,
                retrieved_at=f.retrieved_at,
                licence=f.licence,
                confidence=f.confidence,
            )
            for f in dossier.facts
        ],
        candidates=[
            CandidateRead.model_validate(c, from_attributes=True) for c in dossier.candidates
        ],
        offers=[
            OfferRead(
                job_opportunity_id=o.job_opportunity_id,
                title=o.title,
                source_url=o.source_url,
                first_seen_at=o.first_seen_at,
                closed=o.closed,
                fit_score=o.fit_score,
                recommendation=o.recommendation,
                fit_band=None
                if o.fit_score is None
                else cast(
                    FitBand, band_of(o.fit_score, gated=o.recommendation == "not_recommended")
                ),
                state=o.state,
                is_shortlisted=o.is_shortlisted,
                job_inbox_item_id=o.job_inbox_item_id,
                version=o.version,
            )
            for o in dossier.offers
        ],
        hiring=[HiringWeekRead.model_validate(w, from_attributes=True) for w in dossier.hiring],
        boards=[
            BoardRead(
                source_configuration_id=b.source_configuration_id,
                display_name=b.display_name,
                enabled=b.enabled,
                url=b.url,
            )
            for b in dossier.boards
        ],
        warnings=warnings or [],
    )


@router.get("/companies/{company_id}", response_model=CompanyDossierRead)
async def get_company(
    company_id: int,
    service: Companies,
    default_intent: DefaultIntent,
    search_intent_id: Annotated[int | None, Query(ge=1)] = None,
    include_older: bool = False,
) -> CompanyDossierRead:
    """Return the dossier: sourced facts, pending candidates, offers and the hiring series.

    Offers older than the owner's recency limit are left out unless ``include_older`` is set.
    """
    intent = search_intent_id if search_intent_id is not None else default_intent
    return dossier_read(
        await service.dossier(
            LOCAL_OWNER_ID, company_id, search_intent_id=intent, include_older=include_older
        )
    )


@router.post("/companies/{company_id}/enrich", response_model=CompanyDossierRead)
async def enrich_company(
    company_id: int,
    enrichment: Enrichment,
    service: Companies,
    default_intent: DefaultIntent,
    session: Session,
) -> CompanyDossierRead:
    """Look the company up in the public datasets (Wikidata first) and refresh its facts."""
    result = await enrichment.enrich(LOCAL_OWNER_ID, company_id)
    await session.commit()
    return dossier_read(
        await service.dossier(LOCAL_OWNER_ID, company_id, search_intent_id=default_intent),
        result.warnings,
    )


@router.post(
    "/companies/{company_id}/candidates/{company_enrichment_candidate_id}/confirm",
    response_model=CompanyDossierRead,
)
async def confirm_candidate(
    company_id: int,
    company_enrichment_candidate_id: int,
    enrichment: Enrichment,
    service: Companies,
    default_intent: DefaultIntent,
    session: Session,
) -> CompanyDossierRead:
    """Say that a candidate entity is this company; its facts are stored."""
    await enrichment.confirm(LOCAL_OWNER_ID, company_id, company_enrichment_candidate_id)
    await session.commit()
    return dossier_read(
        await service.dossier(LOCAL_OWNER_ID, company_id, search_intent_id=default_intent)
    )


@router.post(
    "/companies/{company_id}/candidates/{company_enrichment_candidate_id}/reject",
    response_model=CompanyDossierRead,
)
async def reject_candidate(
    company_id: int,
    company_enrichment_candidate_id: int,
    enrichment: Enrichment,
    service: Companies,
    default_intent: DefaultIntent,
    session: Session,
) -> CompanyDossierRead:
    """Say that a candidate entity is not this company; it is not proposed again."""
    await enrichment.reject(LOCAL_OWNER_ID, company_id, company_enrichment_candidate_id)
    await session.commit()
    return dossier_read(
        await service.dossier(LOCAL_OWNER_ID, company_id, search_intent_id=default_intent)
    )


@router.post("/companies/{company_id}/summary", response_model=CompanyDossierRead)
async def write_summary(
    company_id: int,
    summaries: Annotated[CompanySummaryService, Depends(get_company_summary_service)],
    service: Companies,
    default_intent: DefaultIntent,
    session: Session,
) -> CompanyDossierRead:
    """Write the AI summary (labelled AI inference) with the local job-analysis model."""
    await summaries.generate(LOCAL_OWNER_ID, company_id)
    await session.commit()
    return dossier_read(
        await service.dossier(LOCAL_OWNER_ID, company_id, search_intent_id=default_intent)
    )


@router.put("/companies/{company_id}/website", response_model=CompanyDossierRead)
async def set_website(
    company_id: int,
    body: CompanyWebsiteSet,
    service: Companies,
    default_intent: DefaultIntent,
    session: Session,
) -> CompanyDossierRead:
    """Record the company's own website; public datasets then match on its domain."""
    await service.set_website(company_id, body.url)
    await session.commit()
    return dossier_read(
        await service.dossier(LOCAL_OWNER_ID, company_id, search_intent_id=default_intent)
    )


@router.post("/companies/{company_id}/analyse", response_model=CompanyDossierRead)
async def analyse_company(
    company_id: int,
    analysis: Annotated[CompanyAnalysisService, Depends(get_company_analysis_service)],
    service: Companies,
    default_intent: DefaultIntent,
    session: Session,
) -> CompanyDossierRead:
    """Read the company's website and write a cited dossier with the local model (AI inference)."""
    await analysis.analyse(LOCAL_OWNER_ID, company_id)
    await session.commit()
    return dossier_read(
        await service.dossier(LOCAL_OWNER_ID, company_id, search_intent_id=default_intent)
    )
