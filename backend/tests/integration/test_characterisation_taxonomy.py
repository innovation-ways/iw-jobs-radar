"""Characterisation of the taxonomy as the migrations leave it (ADR-080, tests C1 and C9).

The golden files do not import the seed constants: they are the independent record of what an
installation holds today, so later phases (seeds out of run time, packs) cannot lose or rename a term
without a reviewed change to the golden file.
"""

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from tests.golden import check_golden

pytestmark = pytest.mark.integration


async def test_c1_taxonomy_terms_after_migrations(db_session: AsyncSession) -> None:
    """Every term keeps its id, kind, key, label, origin and the version that introduced it."""
    versions = await db_session.execute(
        text("SELECT taxonomy_version_id, description FROM taxonomy_version ORDER BY 1")
    )
    terms = await db_session.execute(
        text(
            "SELECT taxonomy_term_id, kind, term_key, label, origin, "
            "introduced_in_taxonomy_version_id, replaced_by_taxonomy_term_id "
            "FROM taxonomy_term ORDER BY taxonomy_term_id"
        )
    )
    check_golden(
        "taxonomy_after_migrations",
        {
            "versions": [list(row) for row in versions],
            "terms": [list(row) for row in terms],
        },
    )


async def test_c9_taxonomy_endpoint_contract(client: httpx.AsyncClient) -> None:
    """``GET /api/v1/taxonomy`` returns today's terms, grouped, in the same order."""
    response = await client.get("/api/v1/taxonomy")
    assert response.status_code == 200
    check_golden("taxonomy_endpoint", response.json())
