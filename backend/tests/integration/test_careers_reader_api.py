"""Careers pages read through a reader the owner approved (ADR-070 layer 3), with no network."""

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import pytest_asyncio
import respx
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.factories import unique
from tests.job_board_support import build_ats, payload

from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderOutput
from jobs_radar.adapters.sources.detector import Detection, DetectionOutcome
from jobs_radar.adapters.sources.page_config import PageConfigAdapter
from jobs_radar.api.deps import get_page_reader_proposal_service
from jobs_radar.db.models import CollectionRun, PageReaderConfiguration, SourceConfiguration
from jobs_radar.domain.enums import SourceType
from jobs_radar.services.collection import CollectionService
from jobs_radar.services.page_reader_proposal import PageReaderProposalService

pytestmark = pytest.mark.integration

READER: dict[str, Any] = {
    "schema_version": 1,
    "listing_url": "",
    "item_selector": "li.position",
    "title_selector": ".position-title",
    "link_selector": "a.position-link",
    "location_selector": ".position-place",
    "description_selector": ".role-body",
    "next_page_selector": "a.next",
    "fetch_detail": True,
    "max_pages": 3,
}


class Chat:
    provider, model = "ollama", "qwen3:14b"

    async def extract(self, request: ExtractionRequest) -> ProviderOutput:
        keep = ("item_selector", "title_selector", "link_selector", "location_selector")
        return ProviderOutput(json.dumps({k: READER[k] for k in keep}), 1)


class Ai:
    async def direction_target(self, owner_id: int) -> Any:
        return SimpleNamespace(provider_type="ollama"), Chat()


class NoDetector:
    async def detect(self, careers_url: str, *, website_url: str | None = None) -> Detection:
        return Detection(DetectionOutcome.UNSUPPORTED, (), "no known system")


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


@pytest.fixture
def reader_world(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> PageConfigAdapter:
    adapter: PageConfigAdapter = build_ats(PageConfigAdapter)
    monkeypatch.setattr(app.state, "adapters", {SourceType.PAGE_CONFIG: adapter}, raising=False)
    monkeypatch.setattr(app.state, "careers_detector", NoDetector(), raising=False)
    app.dependency_overrides[get_page_reader_proposal_service] = lambda: PageReaderProposalService(
        Ai(), adapter
    )
    yield adapter
    app.dependency_overrides.pop(get_page_reader_proposal_service, None)


class Site(SimpleNamespace):
    """A synthetic careers site with its own host, so sources never collide across tests."""

    origin: str
    careers: str
    reader: dict[str, Any]


@pytest.fixture
def site() -> Site:
    host = f"careers.{unique('co').lower().replace('_', '')}.example"
    origin = f"https://{host}"
    careers = f"{origin}/careers"
    return Site(origin=origin, careers=careers, reader={**READER, "listing_url": careers})


def serve(site: Site) -> None:
    ORIGIN, CAREERS = site.origin, site.careers  # noqa: N806
    respx.get(f"{ORIGIN}/robots.txt").respond(404)
    respx.get(CAREERS, params={"page": "2"}).respond(
        200, content=payload("page_config", "listing_2.html")
    )
    respx.get(CAREERS).respond(200, content=payload("page_config", "listing.html"))
    respx.get(f"{ORIGIN}/careers/roles/platform-engineer").respond(
        200, content=payload("page_config", "detail_platform.html")
    )
    respx.get(f"{ORIGIN}/careers/roles/data-analyst").respond(
        200, content=payload("page_config", "detail_data.html")
    )
    respx.get(f"{ORIGIN}/careers/roles/security-engineer").respond(
        200, content=payload("page_config", "detail_data.html")
    )


def form(site: Site, **extra: Any) -> dict[str, Any]:
    return {
        "name": unique("Synthco"),
        "website_url": f"https://www.{site.origin.removeprefix('https://careers.')}/",
        "careers_url": site.careers,
        **extra,
    }


@respx.mock
async def test_the_proposal_is_previewed_and_nothing_is_saved(
    client: httpx.AsyncClient, reader_world: PageConfigAdapter, site: Site
) -> None:
    serve(site)
    payload_ = form(site)
    response = await client.post("/api/v1/companies/onboarding/propose-reader", json=payload_)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["reader"]["item_selector"] == "li.position"
    assert data["reader"]["listing_url"] == site.careers
    assert [p["title"] for p in data["preview"]] == ["Platform Engineer", "Data Analyst"]
    assert data["proposed_by"].startswith("model:ollama:qwen3:14b")
    listing = await client.get("/api/v1/companies", params={"q": payload_["name"]})
    assert listing.json()["total"] == 0


@respx.mock
async def test_an_approved_reader_creates_a_source_that_the_worker_collects(
    client: httpx.AsyncClient,
    app: FastAPI,
    reader_world: PageConfigAdapter,
    session_factory: async_sessionmaker[AsyncSession],
    site: Site,
) -> None:
    serve(site)
    body = form(site, reader=site.reader, reader_proposed_by="model:ollama:qwen3:14b:reader-v1")
    response = await client.post("/api/v1/companies/onboarding", json=body)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["collecting"] is True

    async with session_factory() as session:
        source = await session.get(SourceConfiguration, data["source_configuration_id"])
        configs = (
            (
                await session.execute(
                    select(PageReaderConfiguration).where(
                        PageReaderConfiguration.source_configuration_id
                        == data["source_configuration_id"]
                    )
                )
            )
            .scalars()
            .all()
        )
    assert source is not None and source.source_type == "page_config"
    assert source.external_identifier == site.careers.removeprefix("https://")
    assert [c.revision for c in configs] == [1]
    assert configs[0].proposed_by == "model:ollama:qwen3:14b:reader-v1"

    await CollectionService(app.state.session_factory, app.state.adapters).run_queued()
    sources = (await client.get("/api/v1/sources")).json()["items"]
    mine = next(
        s for s in sources if s["source_configuration_id"] == data["source_configuration_id"]
    )
    assert mine["last_result"]["outcome"] == "success"
    assert mine["last_result"]["collected_count"] == 3
    assert mine["open_postings"] == 3


async def test_a_reader_and_a_detected_board_together_are_refused(
    client: httpx.AsyncClient, reader_world: PageConfigAdapter, site: Site
) -> None:
    body = form(
        site, reader=site.reader, source={"source_type": "greenhouse", "identifier": "acme"}
    )
    response = await client.post("/api/v1/companies/onboarding", json=body)
    assert response.status_code == 422


@respx.mock
async def test_a_reader_for_another_site_is_refused_and_nothing_is_created(
    client: httpx.AsyncClient, reader_world: PageConfigAdapter, site: Site
) -> None:
    serve(site)
    other = {**site.reader, "listing_url": "https://elsewhere.example/careers"}
    body = form(site, reader=other)
    response = await client.post("/api/v1/companies/onboarding", json=body)
    assert response.status_code == 422
    listing = await client.get("/api/v1/companies", params={"q": body["name"]})
    assert listing.json()["total"] == 0


@respx.mock
async def test_a_reader_that_finds_nothing_is_refused(
    client: httpx.AsyncClient, reader_world: PageConfigAdapter, site: Site
) -> None:
    serve(site)
    body = form(site, reader={**site.reader, "item_selector": "div.nothing"})
    assert (await client.post("/api/v1/companies/onboarding", json=body)).status_code == 422


@respx.mock
async def test_a_new_reader_is_a_new_revision_and_a_stale_version_conflicts(
    client: httpx.AsyncClient,
    reader_world: PageConfigAdapter,
    session_factory: async_sessionmaker[AsyncSession],
    site: Site,
) -> None:
    serve(site)
    created = (
        await client.post("/api/v1/companies/onboarding", json=form(site, reader=site.reader))
    ).json()
    source_id = created["source_configuration_id"]
    version = next(
        s["version"]
        for s in (await client.get("/api/v1/sources")).json()["items"]
        if s["source_configuration_id"] == source_id
    )
    changed = {**site.reader, "fetch_detail": False}
    stale = await client.put(
        f"/api/v1/sources/{source_id}/reader",
        json={"expected_version": version + 5, "reader": changed},
    )
    assert stale.status_code == 409
    ok = await client.put(
        f"/api/v1/sources/{source_id}/reader",
        json={"expected_version": version, "reader": changed, "proposed_by": "owner"},
    )
    assert ok.status_code == 200, ok.text
    async with session_factory() as session:
        revisions = (
            (
                await session.execute(
                    select(PageReaderConfiguration.revision)
                    .where(PageReaderConfiguration.source_configuration_id == source_id)
                    .order_by(PageReaderConfiguration.revision)
                )
            )
            .scalars()
            .all()
        )
    assert revisions == [1, 2]  # the first reader stays in the history


@respx.mock
async def test_a_source_without_a_reader_cannot_get_a_proposal(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    reader_world: PageConfigAdapter,
) -> None:
    from tests.fake_adapter import FakeAdapter

    adapters = {SourceType.GREENHOUSE: FakeAdapter(), SourceType.PAGE_CONFIG: reader_world}
    monkeypatch.setattr(app.state, "adapters", adapters, raising=False)
    source = (
        await client.post(
            "/api/v1/sources",
            json={"source_type": "greenhouse", "external_identifier": unique("board")},
        )
    ).json()
    response = await client.post(
        f"/api/v1/sources/{source['source_configuration_id']}/reader/propose"
    )
    assert response.status_code == 422
