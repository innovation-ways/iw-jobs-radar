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
from jobs_radar.adapters.sources.base import SourceCheckpoint
from jobs_radar.adapters.sources.greenhouse import GreenhouseAdapter
from jobs_radar.core.http import build_http_client
from jobs_radar.core.settings import Settings
from jobs_radar.domain.domains import registered_domain

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
