"""Follow a company from its website and careers addresses (ADR-070), with no network."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.factories import unique
from tests.fake_adapter import FakeAdapter

from jobs_radar.adapters.sources.base import BoardInfo, SourceError
from jobs_radar.adapters.sources.detector import Candidate, Detection, DetectionOutcome
from jobs_radar.db.models import CollectionRun, Company, SourceConfiguration
from jobs_radar.domain.enums import SourceErrorClass, SourceType

pytestmark = pytest.mark.integration


class FakeDetector:
    """Answers every detection with a scripted result and remembers what it was asked."""

    def __init__(self, detection: Detection) -> None:
        self.detection = detection
        self.asked: list[tuple[str, str | None]] = []

    async def detect(self, careers_url: str, *, website_url: str | None = None) -> Detection:
        self.asked.append((careers_url, website_url))
        return self.detection


def found(identifier: str, *, count: int = 12) -> Detection:
    candidate = Candidate(SourceType.GREENHOUSE, identifier, "Synthetic Co", count, "ats")
    return Detection(DetectionOutcome.DETECTED, (candidate,))


@pytest_asyncio.fixture(autouse=True)
async def _only_this_tests_sources(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """Disable earlier tests' sources so queued runs are ours alone."""
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


def install(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, detection: Detection, adapter: FakeAdapter | None
) -> FakeDetector:
    detector = FakeDetector(detection)
    monkeypatch.setattr(app.state, "careers_detector", detector, raising=False)
    monkeypatch.setattr(
        app.state, "adapters", {SourceType.GREENHOUSE: adapter or FakeAdapter()}, raising=False
    )
    return detector


def body(**overrides: Any) -> dict[str, Any]:
    return {
        "name": unique("Acme"),
        "website_url": "https://Acme.example/",
        "careers_url": "https://acme.example/careers/",
        **overrides,
    }


# --- detect -------------------------------------------------------------------------------------


async def test_detect_reports_the_candidates_and_normalised_addresses_and_saves_nothing(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    detector = install(app, monkeypatch, found("acme"), None)
    payload = body(website_url="acme.example", careers_url="http://acme.example/careers/#top")
    response = await client.post("/api/v1/companies/onboarding/detect", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["outcome"] == "detected"
    assert data["website_url"] == "https://acme.example/"
    assert data["careers_url"] == "https://acme.example/careers/"
    assert data["candidates"] == [
        {
            "source_type": "greenhouse",
            "identifier": "acme",
            "display_name": "Synthetic Co",
            "postings_count": 12,
            "layer": "ats",
        }
    ]
    assert data["existing_company_id"] is None
    assert detector.asked == [("https://acme.example/careers/", "https://acme.example/")]
    listing = await client.get("/api/v1/companies", params={"q": payload["name"]})
    assert listing.json()["total"] == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("website_url", "https://boards.greenhouse.io/acme"),
        ("website_url", "not a website"),
        ("careers_url", "https://localhost/jobs"),
        ("careers_url", "ftp://acme.example/jobs"),
    ],
)
async def test_detect_refuses_addresses_that_are_not_public_websites(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    install(app, monkeypatch, found("acme"), None)
    response = await client.post("/api/v1/companies/onboarding/detect", json=body(**{field: value}))
    assert response.status_code == 422
    assert response.json()["error"]["details"]["field"] == field


async def test_a_blank_name_is_refused(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(app, monkeypatch, found("acme"), None)
    response = await client.post("/api/v1/companies/onboarding/detect", json=body(name="   "))
    assert response.status_code == 422


# --- confirm ------------------------------------------------------------------------------------


async def test_confirming_creates_the_company_the_source_and_queues_a_run(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    install(app, monkeypatch, found("acme"), FakeAdapter(board=BoardInfo("Synthetic Co", 12)))
    payload = body(source={"source_type": "greenhouse", "identifier": unique("acme")})
    response = await client.post("/api/v1/companies/onboarding", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["collecting"] is True
    assert data["source_configuration_id"] and data["collection_run_id"]
    assert data["is_followed"] is True

    async with session_factory() as session:
        company = await session.get(Company, data["company_id"])
        source = await session.get(SourceConfiguration, data["source_configuration_id"])
    assert company is not None and source is not None
    assert company.canonical_name == payload["name"]
    assert company.homepage_url == "https://acme.example/"
    assert company.careers_url == "https://acme.example/careers/"
    assert source.company_id == company.company_id
    assert source.display_name == payload["name"]  # the owner's name always wins
    assert source.enabled is True
    assert source.config_json["max_age_days"] == 30  # the opt-in filters are on by default

    listing = await client.get("/api/v1/companies", params={"q": payload["name"]})
    assert listing.json()["items"][0]["is_followed"] is True
    assert listing.json()["items"][0]["has_source"] is True
    runs = await client.get("/api/v1/collection-runs")
    queued = next(
        r for r in runs.json()["items"] if r["collection_run_id"] == data["collection_run_id"]
    )
    assert queued["source_configuration_id"] == data["source_configuration_id"]
    assert queued["status"] == "queued"


async def test_without_the_filters_the_source_keeps_every_posting(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    install(app, monkeypatch, found("acme"), None)
    payload = body(
        source={"source_type": "greenhouse", "identifier": unique("acme")}, filters_enabled=False
    )
    data = (await client.post("/api/v1/companies/onboarding", json=payload)).json()
    async with session_factory() as session:
        source = await session.get(SourceConfiguration, data["source_configuration_id"])
    assert source is not None and not source.config_json


async def test_a_company_without_a_source_is_followed_and_nothing_is_queued(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(app, monkeypatch, Detection(DetectionOutcome.SCRIPT_ONLY, (), "scripts"), None)
    payload = body()
    response = await client.post("/api/v1/companies/onboarding", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["collecting"] is False
    assert data["source_configuration_id"] is None and data["collection_run_id"] is None
    listing = await client.get("/api/v1/companies", params={"q": payload["name"]})
    item = listing.json()["items"][0]
    assert item["is_followed"] is True
    assert item["has_source"] is False  # followed, but nothing is collected automatically
    assert item["careers_url"] == "https://acme.example/careers/"


async def test_a_company_that_already_exists_by_name_gets_the_source_attached(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    install(app, monkeypatch, found("acme"), None)
    name = unique("Acme")
    first = await client.post("/api/v1/companies/onboarding", json=body(name=name))
    second = await client.post(
        "/api/v1/companies/onboarding",
        json=body(
            name=name.upper(), source={"source_type": "greenhouse", "identifier": unique("acme")}
        ),
    )
    assert first.json()["company_id"] == second.json()["company_id"]
    async with session_factory() as session:
        count = len(
            (await session.execute(select(Company).where(Company.name_normalised == name.lower())))
            .scalars()
            .all()
        )
    assert count == 1


async def test_the_same_board_twice_conflicts(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(app, monkeypatch, found("acme"), None)
    source = {"source_type": "greenhouse", "identifier": unique("acme")}
    assert (
        await client.post("/api/v1/companies/onboarding", json=body(source=source))
    ).status_code == 201
    again = await client.post("/api/v1/companies/onboarding", json=body(source=source))
    assert again.status_code == 409


async def test_a_board_that_no_longer_exists_is_refused_and_nothing_is_created(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = SourceError(SourceErrorClass.NOT_FOUND, "The board was not found.")
    install(app, monkeypatch, found("acme"), FakeAdapter(board=missing))
    payload = body(source={"source_type": "greenhouse", "identifier": unique("acme")})
    response = await client.post("/api/v1/companies/onboarding", json=payload)
    assert response.status_code == 422
    listing = await client.get("/api/v1/companies", params={"q": payload["name"]})
    assert listing.json()["total"] == 0


# --- already followed ---------------------------------------------------------------------------


async def test_detect_says_already_followed_when_the_board_is_configured(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = unique("acme")
    install(app, monkeypatch, found(identifier), None)
    payload = body(source={"source_type": "greenhouse", "identifier": identifier})
    assert (await client.post("/api/v1/companies/onboarding", json=payload)).status_code == 201
    detect = await client.post(
        "/api/v1/companies/onboarding/detect", json=body(name=payload["name"])
    )
    data = detect.json()
    assert data["outcome"] == "already_followed"
    assert data["existing_company_id"] is not None


# --- the dossier shows how each source is doing --------------------------------------------------


async def test_the_dossier_lists_the_sources_with_their_type_and_version(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(app, monkeypatch, found("acme"), None)
    payload = body(source={"source_type": "greenhouse", "identifier": unique("acme")})
    created = (await client.post("/api/v1/companies/onboarding", json=payload)).json()
    dossier = (await client.get(f"/api/v1/companies/{created['company_id']}")).json()
    (board,) = dossier["boards"]
    assert board["source_type"] == "greenhouse"
    assert board["version"] >= 1
    assert board["last_outcome"] is None  # nothing has run yet
