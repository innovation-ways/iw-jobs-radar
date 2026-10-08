"""The migration seeds the owner and the taxonomy of document 13, section 2.1."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.domain.taxonomy_seed import TAXONOMY_SEED_V1, label_for

pytestmark = pytest.mark.integration


async def test_the_local_owner_exists(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT owner_id FROM owner"))
    assert result.scalars().all() == [LOCAL_OWNER_ID]


async def test_taxonomy_version_one_exists(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text("SELECT taxonomy_version_id, description FROM taxonomy_version")
    )
    assert [tuple(row) for row in result] == [(1, "seed")]


@pytest.mark.parametrize("kind", sorted(TAXONOMY_SEED_V1))
async def test_every_seed_term_is_present_with_its_label(
    db_session: AsyncSession, kind: str
) -> None:
    result = await db_session.execute(
        text(
            "SELECT term_key, label, origin, introduced_in_taxonomy_version_id FROM taxonomy_term WHERE kind = :k"
        ),
        {"k": kind},
    )
    rows = {row.term_key: row for row in result}
    assert set(rows) == set(TAXONOMY_SEED_V1[kind])
    for key, row in rows.items():
        assert row.label == label_for(key)
        assert row.origin == "seed"
        assert row.introduced_in_taxonomy_version_id == 1


async def test_seed_sizes_match_the_document(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text("SELECT kind, count(*) FROM taxonomy_term GROUP BY kind")
    )
    counts = dict(result.all())  # type: ignore[arg-type]
    assert counts == {
        "role_family": 20, "sector": 17, "seniority_level": 7, "engagement_type": 5,
        "work_arrangement": 3, "employer_type": 3, "benefit": 9,
    }  # fmt: skip
