"""Endpoints to edit the vocabulary of role families and sectors (ADR-080, phase 3).

There is no delete: terms are switched off, never removed, and keys never change.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.api.deps import get_session, get_taxonomy_service
from jobs_radar.db.models import TaxonomyTerm
from jobs_radar.schemas.taxonomy_api import (
    TaxonomyTermAdmin,
    TaxonomyTermCreate,
    TaxonomyTermList,
    TaxonomyTermUpdate,
)
from jobs_radar.services.taxonomy import TaxonomyService

router = APIRouter(prefix="/taxonomy/terms", tags=["taxonomy"])

Service = Annotated[TaxonomyService, Depends(get_taxonomy_service)]
Session = Annotated[AsyncSession, Depends(get_session)]


def _read(term: TaxonomyTerm) -> TaxonomyTermAdmin:
    return TaxonomyTermAdmin(
        kind=term.kind,
        term_key=term.term_key,
        label=term.label,
        origin=term.origin,
        active=term.is_active,
        introduced_in_taxonomy_version_id=term.introduced_in_taxonomy_version_id,
    )


@router.get("", response_model=TaxonomyTermList)
async def list_terms(service: Service) -> TaxonomyTermList:
    """List every role family and sector, including the ones switched off."""
    return TaxonomyTermList(
        taxonomy_version_id=await service.current_version_id(),
        terms=[_read(term) for term in await service.editable_terms()],
    )


@router.post("", response_model=TaxonomyTermAdmin, status_code=201)
async def add_term(
    body: TaxonomyTermCreate, service: Service, session: Session
) -> TaxonomyTermAdmin:
    """Add a role family or a sector; its key is derived from the label."""
    term = await service.add(body.kind, body.label)
    await session.commit()
    return _read(term)


@router.patch("/{kind}/{term_key}", response_model=TaxonomyTermAdmin)
async def update_term(
    kind: str, term_key: str, body: TaxonomyTermUpdate, service: Service, session: Session
) -> TaxonomyTermAdmin:
    """Relabel a term or switch it off or on; a repeated request changes nothing."""
    term = await service.update(kind, term_key, label=body.label, active=body.active)
    await session.commit()
    return _read(term)
