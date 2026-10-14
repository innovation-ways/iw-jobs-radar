"""A company's own site with structured postings, from detection to collection (ADR-070 layer 2)."""

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
import respx
from fastapi import FastAPI
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.factories import unique
from tests.job_board_support import build_ats, payload

from jobs_radar.adapters.sources.detector import CareersDetector
from jobs_radar.adapters.sources.page_jsonld import PageJsonLdAdapter
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.core.url_guard import UrlGuard
from jobs_radar.db.models import CollectionRun, SourceConfiguration
from jobs_radar.domain.enums import SourceType
from jobs_radar.services.collection import CollectionService

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def _only_this_tests_sources(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    async with session_factory() as session:
        await session.execute(update(SourceConfiguration).values(enabled=False))
        await session.commit()
    yield
    # The runs these tests queue are never executed here; leave none for the next test's worker.
    async with session_factory() as session:
        await session.execute(
            update(CollectionRun).where(CollectionRun.status == "queued").values(status="cancelled")
        )
        await session.commit()


@respx.mock
async def test_a_site_with_structured_postings_is_detected_followed_and_collected(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = f"careers.{unique('co').lower().replace('_', '')}.example"
    origin = f"https://{host}"
    respx.get(f"{origin}/robots.txt").respond(
        200, text=f"User-agent: *\nSitemap: {origin}/sitemap.xml\n"
    )
    respx.get(f"{origin}/").respond(
        200, html="<html><body><h1>Careers</h1><p>" + "open roles " * 40 + "</p></body></html>"
    )
    sitemap = payload("page_jsonld", "sitemap_vacancies.xml").decode()
    sitemap = sitemap.replace("careers.synthco.example", host).replace(
        "https://elsewhere.example/job/not-ours-1", f"{origin}/job/data-engineer-4053"
    )
    respx.get(f"{origin}/sitemap.xml").respond(200, text=sitemap)
    pages = {
        "senior-platform-engineer-4052": "posting_wise_like.html",
        "data-engineer-4053": "posting_remote_graph.html",
        "closed-role-4000": "posting_expired.html",
    }
    for slug, fixture in pages.items():
        respx.get(f"{origin}/job/{slug}").respond(200, content=payload("page_jsonld", fixture))
    respx.get(f"{origin}/job/gone-4001").respond(404)

    adapter = build_ats(PageJsonLdAdapter)

    async def resolve(_: str) -> list[str]:
        return ["93.184.216.34"]

    detector = CareersDetector(
        GuardedHttpClient(guard=UrlGuard(resolver=resolve), user_agent="JobsRadar/test"),
        {SourceType.PAGE_JSONLD: adapter},
    )
    monkeypatch.setattr(app.state, "adapters", {SourceType.PAGE_JSONLD: adapter}, raising=False)
    monkeypatch.setattr(app.state, "careers_detector", detector, raising=False)

    form = {
        "name": unique("Synthco"),
        "website_url": f"https://www.{host.removeprefix('careers.')}/",
        "careers_url": f"{origin}/",
    }
    detected = (await client.post("/api/v1/companies/onboarding/detect", json=form)).json()
    assert detected["outcome"] == "detected"
    candidate = detected["candidates"][0]
    assert candidate["source_type"] == "page_jsonld"
    assert candidate["layer"] == "structured_page"

    confirm = {
        **form,
        "source": {"source_type": "page_jsonld", "identifier": candidate["identifier"]},
    }
    created = await client.post("/api/v1/companies/onboarding", json=confirm)
    assert created.status_code == 201, created.text

    await CollectionService(app.state.session_factory, app.state.adapters).run_queued()
    sources = (await client.get("/api/v1/sources")).json()["items"]
    mine = next(
        s
        for s in sources
        if s["source_configuration_id"] == created.json()["source_configuration_id"]
    )
    assert mine["last_result"]["outcome"] == "success"
    assert mine["open_postings"] == 2  # the expired and the missing page are not postings

    # The dossier says how many postings the owner's filters left out, and that filters are on.
    dossier = (await client.get(f"/api/v1/companies/{created.json()['company_id']}")).json()
    (board,) = dossier["boards"]
    assert board["filters_enabled"] is True
    assert board["last_dropped_count"] == mine["last_result"]["dropped_count"]
    assert board["last_dropped_count"] >= 2  # the expired and the missing page, at least
