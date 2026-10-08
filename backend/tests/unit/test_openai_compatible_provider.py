"""OpenAI-compatible adapter: request shape, key handling, SSRF and classified failures (T6.2)."""

import json

import httpx
import pytest
import respx

from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderError
from jobs_radar.adapters.providers.openai_compatible import OpenAiCompatibleProvider
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.core.url_guard import UrlGuard
from jobs_radar.domain.enums import ProviderErrorClass

BASE = "https://api.example.test/v1"
SECRET = "sk-test-do-not-leak"
SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
REQUEST = ExtractionRequest(system="Extract.", user="CV text.", json_schema=SCHEMA)


def provider(base: str = BASE, resolved: str = "93.184.216.34") -> OpenAiCompatibleProvider:
    async def resolve(host: str) -> list[str]:
        return [resolved]

    client = GuardedHttpClient(guard=UrlGuard(resolver=resolve), user_agent="JobsRadar/test")
    return OpenAiCompatibleProvider(client, base_url=base, model="gpt-test", api_key=SECRET)


@respx.mock
async def test_extract_posts_a_schema_constrained_chat_completion_with_the_bearer_key() -> None:
    route = respx.post(f"{BASE}/chat/completions").respond(
        200, json={"choices": [{"message": {"role": "assistant", "content": '{"name": "x"}'}}]}
    )
    output = await provider().extract(REQUEST)

    request = route.calls.last.request
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    body = json.loads(request.read())
    assert body["model"] == "gpt-test"
    assert body["temperature"] == 0
    assert body["messages"] == [
        {"role": "system", "content": "Extract."},
        {"role": "user", "content": "CV text."},
    ]
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert output.content == '{"name": "x"}'


@respx.mock
async def test_the_trailing_slash_of_the_base_url_is_ignored() -> None:
    respx.post(f"{BASE}/chat/completions").respond(
        200, json={"choices": [{"message": {"content": "{}"}}]}
    )
    assert (await provider(base=f"{BASE}/").extract(REQUEST)).content == "{}"


@respx.mock
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ProviderErrorClass.UNAUTHORIZED),
        (403, ProviderErrorClass.UNAUTHORIZED),
        (404, ProviderErrorClass.MODEL_NOT_FOUND),
        (429, ProviderErrorClass.RATE_LIMITED),
        (500, ProviderErrorClass.HTTP_ERROR),
    ],
)
async def test_http_failures_are_classified_without_leaking_the_key_or_body(
    status: int, expected: ProviderErrorClass
) -> None:
    respx.post(f"{BASE}/chat/completions").respond(status, text=f"echo {SECRET} CV text")
    with pytest.raises(ProviderError) as caught:
        await provider().extract(REQUEST)
    assert caught.value.error_class is expected
    assert SECRET not in str(caught.value) and "CV text" not in str(caught.value)


@respx.mock
async def test_an_unusable_answer_is_invalid_response() -> None:
    respx.post(f"{BASE}/chat/completions").respond(200, json={"choices": []})
    with pytest.raises(ProviderError) as caught:
        await provider().extract(REQUEST)
    assert caught.value.error_class is ProviderErrorClass.INVALID_RESPONSE


@respx.mock
async def test_a_timeout_and_a_network_error_are_classified() -> None:
    respx.post(f"{BASE}/chat/completions").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderError) as caught:
        await provider().extract(REQUEST)
    assert caught.value.error_class is ProviderErrorClass.TIMEOUT
    respx.post(f"{BASE}/chat/completions").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(ProviderError) as caught:
        await provider().extract(REQUEST)
    assert caught.value.error_class is ProviderErrorClass.UNAVAILABLE


async def test_private_and_metadata_addresses_are_refused_before_any_request() -> None:
    for resolved in ("10.0.0.5", "169.254.169.254", "127.0.0.1"):
        with pytest.raises(ProviderError) as caught:
            await provider(resolved=resolved).extract(REQUEST)
        assert caught.value.error_class is ProviderErrorClass.BLOCKED_URL


async def test_plain_http_is_refused() -> None:
    with pytest.raises(ProviderError) as caught:
        await provider(base="http://api.example.test/v1").extract(REQUEST)
    assert caught.value.error_class is ProviderErrorClass.BLOCKED_URL


@respx.mock
async def test_models_are_listed_sorted() -> None:
    respx.get(f"{BASE}/models").respond(
        200, json={"data": [{"id": "b-model"}, {"id": "a-model"}, {"id": "a-model"}]}
    )
    assert await provider().available_models() == ["a-model", "b-model"]
    assert respx.calls.last.request.headers["authorization"] == f"Bearer {SECRET}"


@respx.mock
async def test_listing_models_fails_cleanly_when_unsupported() -> None:
    respx.get(f"{BASE}/models").respond(404)
    with pytest.raises(ProviderError):
        await provider().available_models()


def test_the_repr_hides_the_key() -> None:
    assert SECRET not in repr(provider())
