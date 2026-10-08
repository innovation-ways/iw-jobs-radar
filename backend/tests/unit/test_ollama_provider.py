"""Ollama adapter: request shape, determinism settings and classified failures (T4.1)."""

import json

import httpx
import pytest
import respx
from pydantic import SecretStr

from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderError
from jobs_radar.adapters.providers.ollama import OllamaProvider, build_ollama_provider
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.core.settings import Settings
from jobs_radar.core.url_guard import UrlGuard
from jobs_radar.domain.enums import ProviderErrorClass

BASE = "http://host.docker.internal:11434"
SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}
REQUEST = ExtractionRequest(system="Extract.", user="Job text.", json_schema=SCHEMA)


def provider(model: str = "qwen3:8b") -> OllamaProvider:
    async def resolve(host: str) -> list[str]:
        return ["172.17.0.1"]

    guard = UrlGuard(
        resolver=resolve,
        allow_private=True,
        allowed_private_hosts=frozenset({"host.docker.internal"}),
    )
    client = GuardedHttpClient(guard=guard, user_agent="JobsRadar/test")
    return OllamaProvider(client, base_url=BASE, model=model, timeout_seconds=60)


@respx.mock
async def test_extract_posts_a_deterministic_schema_constrained_chat_request() -> None:
    route = respx.post(f"{BASE}/api/chat").respond(
        200, json={"message": {"role": "assistant", "content": '{"title": "x"}'}, "done": True}
    )
    output = await provider().extract(REQUEST)

    body = json.loads(route.calls.last.request.read())
    assert body["model"] == "qwen3:8b"
    assert body["stream"] is False
    assert body["format"] == SCHEMA  # the output is constrained by the JSON schema
    assert body["think"] is False  # no reasoning mode: faster and repeatable
    assert body["options"]["temperature"] == 0
    assert body["options"]["seed"] == 0
    assert body["messages"] == [
        {"role": "system", "content": "Extract."},
        {"role": "user", "content": "Job text."},
    ]
    assert output.content == '{"title": "x"}'
    assert output.latency_ms >= 0


@respx.mock
async def test_the_provider_identifies_itself_for_the_stored_extraction() -> None:
    p = provider("gemma3:12b")
    assert (p.provider, p.model) == ("ollama", "gemma3:12b")


@respx.mock
@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (
            httpx.Response(404, json={"error": "model 'qwen3:8b' not found"}),
            ProviderErrorClass.MODEL_NOT_FOUND,
        ),
        (httpx.Response(500, json={"error": "boom"}), ProviderErrorClass.HTTP_ERROR),
        (httpx.Response(200, content=b"not json"), ProviderErrorClass.INVALID_RESPONSE),
        (httpx.Response(200, json={"unexpected": True}), ProviderErrorClass.INVALID_RESPONSE),
        (
            httpx.Response(200, json={"message": {"content": 5}}),
            ProviderErrorClass.INVALID_RESPONSE,
        ),
    ],
)
async def test_bad_answers_are_classified(
    answer: httpx.Response, expected: ProviderErrorClass
) -> None:
    respx.post(f"{BASE}/api/chat").mock(return_value=answer)
    with pytest.raises(ProviderError) as error:
        await provider().extract(REQUEST)
    assert error.value.error_class is expected


@respx.mock
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (httpx.ConnectError("refused"), ProviderErrorClass.UNAVAILABLE),
        (httpx.ReadTimeout("slow"), ProviderErrorClass.TIMEOUT),
    ],
)
async def test_transport_failures_are_classified(
    failure: Exception, expected: ProviderErrorClass
) -> None:
    respx.post(f"{BASE}/api/chat").mock(side_effect=failure)
    with pytest.raises(ProviderError) as error:
        await provider().extract(REQUEST)
    assert error.value.error_class is expected


@respx.mock
async def test_errors_never_contain_the_prompt_or_the_job_text() -> None:
    respx.post(f"{BASE}/api/chat").respond(500, json={"error": "Job text. leaked?"})
    with pytest.raises(ProviderError) as error:
        await provider().extract(REQUEST)
    assert "Job text" not in error.value.message and "Extract." not in error.value.message


async def test_a_blocked_address_is_reported_as_blocked() -> None:
    guard = UrlGuard()  # no local policy: the host is refused
    client = GuardedHttpClient(guard=guard, user_agent="JobsRadar/test")
    with pytest.raises(ProviderError) as error:
        await OllamaProvider(client, base_url=BASE, model="m").extract(REQUEST)
    assert error.value.error_class is ProviderErrorClass.BLOCKED_URL


@respx.mock
async def test_available_models_lists_installed_models() -> None:
    respx.get(f"{BASE}/api/tags").respond(
        200, json={"models": [{"name": "qwen3:8b"}, {"name": "qwen3-embedding:8b"}]}
    )
    assert await provider().available_models() == ["qwen3:8b", "qwen3-embedding:8b"]


def test_the_factory_allows_only_the_configured_ollama_host_when_local_providers_are_on() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        db_password=SecretStr("x"),
        allow_local_providers=True,
        ollama_url="http://host.docker.internal:11434",
    )
    built = build_ollama_provider(settings, model="qwen3:8b")
    assert (built.provider, built.model) == ("ollama", "qwen3:8b")
