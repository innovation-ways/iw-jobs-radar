"""The taxonomy repository gives the vocabulary that code used to import from seed modules (ADR-080)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.golden import golden_optional_terms, golden_taxonomy

from jobs_radar.repositories.taxonomy import TaxonomyRepository

pytestmark = pytest.mark.integration


async def test_keys_in_order_follow_the_creation_order_of_the_terms(
    db_session: AsyncSession,
) -> None:
    """Forms and the demo list the terms in the order the migrations created them."""
    assert await TaxonomyRepository(db_session).keys_in_order() == golden_taxonomy()


async def test_optional_keys_are_the_terms_added_after_version_one(
    db_session: AsyncSession,
) -> None:
    """ADR-073: an intent saved before a term existed does not have to list it."""
    optional = await TaxonomyRepository(db_session).optional_keys_by_kind()
    assert optional == golden_optional_terms()
    assert "contractor_agency" in optional["engagement_type"]
    assert "finance_accounting" in optional["role_family"]
