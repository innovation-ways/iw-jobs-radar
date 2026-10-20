"""The migration seeds the owner and the taxonomy of document 13, section 2.1."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.domain.taxonomy_additions import TAXONOMY_V2_ADDITIONS, V2_LABELS
from jobs_radar.domain.taxonomy_seed import TAXONOMY_SEED_V1, label_for
from jobs_radar.domain.taxonomy_v3 import TAXONOMY_V3_ADDITIONS, V3_LABELS
from jobs_radar.domain.taxonomy_v4 import TAXONOMY_V4_ADDITIONS, V4_LABELS

pytestmark = pytest.mark.integration


async def test_the_local_owner_exists(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT owner_id FROM owner"))
    assert result.scalars().all() == [LOCAL_OWNER_ID]


async def test_taxonomy_versions_are_the_seed_and_the_non_technical_families(
    db_session: AsyncSession,
) -> None:
    result = await db_session.execute(
        text(
            "SELECT taxonomy_version_id, description FROM taxonomy_version "
            "ORDER BY taxonomy_version_id"
        )
    )
    rows = [tuple(row) for row in result]
    assert [version for version, _ in rows] == [1, 2, 3, 4]
    assert rows[0][1] == "seed"


async def test_version_two_adds_the_non_technical_role_families_with_their_labels(
    db_session: AsyncSession,
) -> None:
    """ADR-060: finance and other non-technical families, so the model can classify them."""
    result = await db_session.execute(
        text(
            "SELECT kind, term_key, label, origin, introduced_in_taxonomy_version_id "
            "FROM taxonomy_term WHERE introduced_in_taxonomy_version_id = 2"
        )
    )
    rows = {(row.kind, row.term_key): row for row in result}
    expected = {(kind, key) for kind, keys in TAXONOMY_V2_ADDITIONS.items() for key in keys}
    assert set(rows) == expected
    assert ("role_family", "finance_accounting") in expected
    for (_kind, key), row in rows.items():
        assert row.label == V2_LABELS[key]
        assert row.origin == "seed"


async def test_version_three_adds_the_agency_contract_engagement_type(
    db_session: AsyncSession,
) -> None:
    """ADR-073: a contract placed through an agency is its own engagement type."""
    result = await db_session.execute(
        text(
            "SELECT kind, term_key, label, origin FROM taxonomy_term "
            "WHERE introduced_in_taxonomy_version_id = 3"
        )
    )
    rows = {(row.kind, row.term_key): row for row in result}
    expected = {(kind, key) for kind, keys in TAXONOMY_V3_ADDITIONS.items() for key in keys}
    assert set(rows) == expected
    assert ("engagement_type", "contractor_agency") in expected
    for (_kind, key), row in rows.items():
        assert row.label == V3_LABELS[key]
        assert row.origin == "seed"


async def test_version_four_adds_the_schedule_and_travel_vocabularies(
    db_session: AsyncSession,
) -> None:
    """ADR-080, phase 6b: working patterns and how much travel a job involves."""
    result = await db_session.execute(
        text(
            "SELECT kind, term_key, label, origin FROM taxonomy_term "
            "WHERE introduced_in_taxonomy_version_id = 4"
        )
    )
    rows = {(row.kind, row.term_key): row for row in result}
    expected = {(kind, key) for kind, keys in TAXONOMY_V4_ADDITIONS.items() for key in keys}
    assert set(rows) == expected
    assert expected == {
        ("schedule", "day"),
        ("schedule", "night"),
        ("schedule", "rotating_shifts"),
        ("schedule", "weekends"),
        ("schedule", "on_call"),
        ("travel_level", "none"),
        ("travel_level", "occasional"),
        ("travel_level", "frequent"),
    }
    for (_kind, key), row in rows.items():
        assert row.label == V4_LABELS[key] and row.origin == "seed"


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
    rows = {row.term_key: row for row in result if row.introduced_in_taxonomy_version_id == 1}
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
        "role_family": 26, "sector": 17, "seniority_level": 7, "engagement_type": 6,
        "work_arrangement": 3, "employer_type": 3, "benefit": 9,
        "schedule": 5, "travel_level": 3,
    }  # fmt: skip
