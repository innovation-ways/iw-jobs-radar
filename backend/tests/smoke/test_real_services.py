"""Opt-in smoke tests against real services (T8.3). Never part of the default run.

Run with ``make smoke`` (``JOBS_RADAR_SMOKE=1``). They need the network (and, for the model
tests, a local Ollama or a cloud key) and use only synthetic text; they read public data and send
no personal data. Each test skips itself when its service is not available.
"""

import json
import os

import pytest
from pydantic import SecretStr

from jobs_radar.adapters.enrichment.base import PublicApi
from jobs_radar.adapters.enrichment.wikidata import WikidataAdapter
from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderError
from jobs_radar.adapters.providers.factory import ProviderSpec, build_provider
from jobs_radar.adapters.sources.arbeitnow import ArbeitnowAdapter
from jobs_radar.adapters.sources.ashby import AshbyAdapter
from jobs_radar.adapters.sources.base import SourceCheckpoint
from jobs_radar.adapters.sources.eightfold import EightfoldAdapter
from jobs_radar.adapters.sources.greenhouse import GreenhouseAdapter
from jobs_radar.adapters.sources.himalayas import HimalayasAdapter
from jobs_radar.adapters.sources.jobicy import JobicyAdapter
from jobs_radar.adapters.sources.lever import LeverAdapter
from jobs_radar.adapters.sources.smartrecruiters import SmartRecruitersAdapter
from jobs_radar.core.http import build_http_client
from jobs_radar.core.settings import Settings
from jobs_radar.domain.domains import registered_domain
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters

pytestmark = pytest.mark.skipif(
    os.environ.get("JOBS_RADAR_SMOKE") != "1",
    reason="opt-in: run `make smoke` (uses the network)",
)


def settings() -> Settings:
    return Settings(
        db_password=SecretStr("unused"),
        allow_local_providers=True,
        ollama_url=os.environ.get("JOBS_RADAR_SMOKE_OLLAMA_URL", "http://127.0.0.1:11434"),
    )


async def test_a_real_greenhouse_board_validates_and_lists_jobs() -> None:
    adapter = GreenhouseAdapter(build_http_client())
    board = await adapter.validate("anthropic")
    assert board.name
    result = await adapter.collect(
        SourceCheckpoint("anthropic", adapter.endpoint("anthropic"), None, rate_limit_per_minute=6)
    )
    assert len(result.postings) > 0
    assert all(p.title and p.source_url.startswith("https://") for p in result.postings[:20])


@pytest.mark.parametrize(
    ("adapter_class", "key"),
    [(ArbeitnowAdapter, "arbeitnow"), (JobicyAdapter, "jobicy"), (HimalayasAdapter, "himalayas")],
)
async def test_a_real_job_board_returns_postings_with_a_company_and_a_link(
    adapter_class: type, key: str
) -> None:
    adapter = adapter_class(build_http_client())
    # A small, synthetic scope and a low limit: one polite request or a few, no personal data.
    scope = LocationScope(frozenset({"PT"}), include_worldwide=True)
    filters = JobBoardFilters(max_postings_per_run=10, max_age_days=60)
    result = await adapter.collect(
        SourceCheckpoint(key, adapter.endpoint(key), None, 6, filters=filters, scope=scope)
    )
    assert result.postings, f"{key} returned no posting that passes the filters"
    for posting in result.postings:
        assert posting.company_name and posting.title
        assert posting.source_url.startswith("https://")


@pytest.mark.parametrize(
    ("adapter_class", "identifier"),
    [
        (LeverAdapter, "spotify"),
        (AshbyAdapter, "ashby"),
        (SmartRecruitersAdapter, "BoschGroup"),
        (EightfoldAdapter, "jobs.amdocs.com"),
    ],
)
async def test_a_real_company_board_validates_and_lists_postings(
    adapter_class: type, identifier: str
) -> None:
    # SmartRecruiters and Eightfold need one request per posting, so only three details are read.
    adapter = (
        adapter_class(build_http_client(), max_details=3)
        if adapter_class in (SmartRecruitersAdapter, EightfoldAdapter)
        else adapter_class(build_http_client())
    )
    info = await adapter.validate(identifier)
    assert info.name and info.postings_count > 0
    result = await adapter.collect(
        SourceCheckpoint(identifier, adapter.endpoint(identifier), None, rate_limit_per_minute=30)
    )
    assert result.postings
    for posting in result.postings[:20]:
        assert posting.title and posting.source_url.startswith("https://")


async def test_real_wikidata_finds_the_company_and_its_website() -> None:
    adapter = WikidataAdapter(PublicApi(build_http_client(), min_interval=1.0))
    found = await adapter.find("Anthropic")
    assert found, "Wikidata returned no company for 'Anthropic'"
    assert any(registered_domain(c.website or "") == "anthropic.com" for c in found)


async def test_a_real_local_model_answers_a_schema_constrained_request() -> None:
    model = os.environ.get("JOBS_RADAR_SMOKE_MODEL", "qwen3:8b")
    provider = build_provider(ProviderSpec("ollama", settings().ollama_url, model), settings())
    try:
        models = await provider.available_models()
    except ProviderError as error:
        pytest.skip(f"local model server not available: {error.error_class.value}")
    if model not in models:
        pytest.skip(f"model {model} is not installed")
    schema = {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}
    output = await provider.extract(
        ExtractionRequest(
            system="Answer with a JSON object only.",
            user="The office is in Lisbon, Portugal. Which city is the office in?",
            json_schema=schema,
        )
    )
    assert "lisbon" in json.loads(output.content)["city"].lower()


async def test_a_real_cloud_provider_lists_models() -> None:
    key = os.environ.get("JOBS_RADAR_SMOKE_API_KEY")
    url = os.environ.get("JOBS_RADAR_SMOKE_API_URL")
    if not key or not url:
        pytest.skip(
            "set JOBS_RADAR_SMOKE_API_URL and JOBS_RADAR_SMOKE_API_KEY to test a cloud provider"
        )
    provider = build_provider(ProviderSpec("compatible", url, "unused", key), settings())
    assert await provider.available_models()  # a model list only: no document or job text is sent


async def test_real_careers_addresses_are_detected() -> None:
    """ADR-070: a board address resolves to its board, and an own site to structured postings."""
    from jobs_radar.adapters.sources.detector import CareersDetector, DetectionOutcome
    from jobs_radar.adapters.sources.page_jsonld import PageJsonLdAdapter
    from jobs_radar.domain.enums import SourceType

    client = build_http_client()
    detector = CareersDetector(
        client,
        {SourceType.ASHBY: AshbyAdapter(client), SourceType.PAGE_JSONLD: PageJsonLdAdapter(client)},
    )
    board = await detector.detect("https://jobs.ashbyhq.com/mistral.ai")
    assert board.outcome is DetectionOutcome.DETECTED
    assert board.candidates[0].identifier == "mistral.ai"
    assert board.candidates[0].postings_count > 0

    own_site = await detector.detect("https://wise.jobs/", website_url="https://wise.com/")
    assert own_site.outcome is DetectionOutcome.DETECTED
    assert own_site.candidates[0].source_type is SourceType.PAGE_JSONLD
    assert own_site.candidates[0].postings_count > 0
