"""Adapter for OpenAI-compatible chat APIs (OpenAI, MiniMax and other compatible servers; ADR-035).

Structured output uses ``response_format: json_schema``. The API key goes only in the
``Authorization`` header of a guarded request (HTTPS, public addresses only); it is never part of an
error message, a log line or the ``repr``. Errors are classified and carry no prompt, answer or key.
"""

import json
import time
from collections.abc import Awaitable

from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderError, ProviderOutput
from jobs_radar.core.http import FetchError, GuardedHttpClient, HttpResponse
from jobs_radar.domain.enums import ProviderErrorClass

_FETCH_CLASSES = {
    "blocked_url": ProviderErrorClass.BLOCKED_URL,
    "timeout": ProviderErrorClass.TIMEOUT,
    "network_error": ProviderErrorClass.UNAVAILABLE,
    "too_many_redirects": ProviderErrorClass.UNAVAILABLE,
    "too_large": ProviderErrorClass.INVALID_RESPONSE,
}
_STATUS_CLASSES = {
    401: ProviderErrorClass.UNAUTHORIZED,
    403: ProviderErrorClass.UNAUTHORIZED,
    404: ProviderErrorClass.MODEL_NOT_FOUND,
    429: ProviderErrorClass.RATE_LIMITED,
}
_MESSAGES = {
    ProviderErrorClass.UNAVAILABLE: "The AI provider is not reachable.",
    ProviderErrorClass.TIMEOUT: "The AI provider did not answer in time.",
    ProviderErrorClass.MODEL_NOT_FOUND: "The AI provider does not know the configured model.",
    ProviderErrorClass.INVALID_RESPONSE: "The AI provider returned an unusable answer.",
    ProviderErrorClass.BLOCKED_URL: "The AI provider address is not allowed.",
    ProviderErrorClass.HTTP_ERROR: "The AI provider reported an error.",
    ProviderErrorClass.UNAUTHORIZED: "The AI provider refused the credential.",
    ProviderErrorClass.RATE_LIMITED: "The AI provider is limiting requests; try again later.",
}
# Cap on generated tokens, so a model that loops cannot run (and bill) until the timeout.
_MAX_TOKENS = 4096


def _error(error_class: ProviderErrorClass) -> ProviderError:
    return ProviderError(error_class, _MESSAGES[error_class])


class OpenAiCompatibleProvider:
    """Structured extraction through an OpenAI-compatible ``/chat/completions`` endpoint."""

    def __init__(
        self,
        client: GuardedHttpClient,
        *,
        base_url: str,
        model: str,
        api_key: str,
        provider: str = "compatible",
        timeout_seconds: float = 120.0,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self.model = model
        self.provider = provider
        self._api_key = api_key
        self._timeout = timeout_seconds

    def __repr__(self) -> str:
        return f"OpenAiCompatibleProvider(provider={self.provider!r}, model={self.model!r})"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    async def extract(self, request: ExtractionRequest) -> ProviderOutput:
        """Send the request and return the model's JSON text.

        Raises:
            ProviderError: blocked address, unreachable, timeout, refused credential, unknown
                model, rate limit, error status or unusable answer.
        """
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": _MAX_TOKENS,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "extraction", "schema": request.json_schema},
            },
        }
        started = time.monotonic()
        response = await self._call(
            self._client.post_json(
                f"{self._base_url}/chat/completions",
                payload,
                headers=self._headers(),
                timeout=self._timeout,
            )
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        self._check_status(response)
        try:
            content = json.loads(response.body)["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise _error(ProviderErrorClass.INVALID_RESPONSE) from exc
        if not isinstance(content, str):
            raise _error(ProviderErrorClass.INVALID_RESPONSE)
        return ProviderOutput(content=content, latency_ms=latency_ms)

    async def available_models(self) -> list[str]:
        """Sorted ids of the models the provider offers (``GET /models``).

        Raises:
            ProviderError: the provider does not support listing, or the call failed.
        """
        response = await self._call(
            self._client.get(f"{self._base_url}/models", headers=self._headers())
        )
        self._check_status(response)
        try:
            return sorted({str(item["id"]) for item in json.loads(response.body)["data"]})
        except (ValueError, KeyError, TypeError) as exc:
            raise _error(ProviderErrorClass.INVALID_RESPONSE) from exc

    @staticmethod
    async def _call(pending: Awaitable[HttpResponse]) -> HttpResponse:
        try:
            return await pending
        except FetchError as exc:
            raise _error(
                _FETCH_CLASSES.get(exc.error_class, ProviderErrorClass.UNAVAILABLE)
            ) from exc

    @staticmethod
    def _check_status(response: HttpResponse) -> None:
        if response.status == 200:
            return
        raise _error(_STATUS_CLASSES.get(response.status, ProviderErrorClass.HTTP_ERROR))
