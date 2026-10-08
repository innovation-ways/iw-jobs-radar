"""Seeding the development watchlist: disabled, idempotent and without any network."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.sources.greenhouse import GreenhouseAdapter
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.core.url_guard import UrlGuard
from jobs_radar.db.models import Company, SourceConfiguration
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.tools.seed_dev_sources import DEV_BOARDS, seed_dev_sources

pytestmark = pytest.mark.integration


def adapter() -> GreenhouseAdapter:
    """A real adapter; the network is blocked in tests, so any request would fail loudly."""
    return GreenhouseAdapter(GuardedHttpClient(guard=UrlGuard(), user_agent="test"))


async def seeded(session: AsyncSession) -> list[SourceConfiguration]:
    tokens = [token for token, _ in DEV_BOARDS]
    rows = await session.execute(
        select(SourceConfiguration).where(SourceConfiguration.external_identifier.in_(tokens))
    )
    return list(rows.scalars())


async def test_seeding_adds_every_board_disabled_with_its_company(db_session: AsyncSession) -> None:
    created = await seed_dev_sources(db_session, adapter(), LOCAL_OWNER_ID)
    assert created == len(DEV_BOARDS)

    sources = {s.external_identifier: s for s in await seeded(db_session)}
    assert set(sources) == {token for token, _ in DEV_BOARDS}
    for token, name in DEV_BOARDS:
        source = sources[token]
        assert source.enabled is False
        assert source.source_type == "greenhouse"
        assert source.display_name == name
        assert source.url == f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        company = await db_session.get(Company, source.company_id)
        assert company is not None and company.canonical_name == name


async def test_seeding_twice_adds_nothing_and_keeps_changes(db_session: AsyncSession) -> None:
    await seed_dev_sources(db_session, adapter(), LOCAL_OWNER_ID)
    anthropic = next(s for s in await seeded(db_session) if s.external_identifier == "anthropic")
    anthropic.enabled = True  # the owner enabled it in the GUI
    await db_session.flush()

    assert await seed_dev_sources(db_session, adapter(), LOCAL_OWNER_ID) == 0
    await db_session.refresh(anthropic)
    assert anthropic.enabled is True
    count = await db_session.scalar(
        select(func.count())
        .select_from(SourceConfiguration)
        .where(SourceConfiguration.external_identifier == "anthropic")
    )
    assert count == 1
