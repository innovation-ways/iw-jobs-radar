"""Minimal Ollama adapter (ADR-035, ADR-038, ADR-039).

Uses ``/api/chat`` with a JSON-schema ``format``, temperature 0, a fixed seed and no reasoning
mode, so the same text gives the same answer. The host Ollama is reached from containers through
``host.docker.internal``; it is allowed only when ``JOBS_RADAR_ALLOW_LOCAL_PROVIDERS`` is on and the
host is the configured one. Errors are classified and never include prompts or answers.
"""

import json
import time
from collections.abc import Awaitable
from urllib.parse import urlsplit

from jobs_radar import __version__
from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderError, ProviderOutput
from jobs_radar.core.http import FetchError, GuardedHttpClient, HttpResponse
from jobs_radar.core.settings import Settings
from jobs_radar.core.url_guard import UrlGuard
from jobs_radar.domain.enums import ProviderErrorClass

# Context window requested from the model: the description (12,000 characters) plus instructions.
_NUM_CTX = 16384
# Cap on generated tokens. A normal extraction is well under 2,000 tokens; without a cap a model
# that falls into a repetition loop keeps generating until the request times out.
_NUM_PREDICT = 4096

_FETCH_CLASSES = {
    "blocked_url": ProviderErrorClass.BLOCKED_URL,
    "timeout": ProviderErrorClass.TIMEOUT,
    "network_error": ProviderErrorClass.UNAVAILABLE,
    "too_many_redirects": ProviderErrorClass.UNAVAILABLE,
    "too_large": ProviderErrorClass.INVALID_RESPONSE,
}
_MESSAGES = {
    ProviderErrorClass.UNAVAILABLE: "The local AI model server is not reachable.",
    ProviderErrorClass.TIMEOUT: "The local AI model did not answer in time.",
    ProviderErrorClass.MODEL_NOT_FOUND: "The configured AI model is not installed.",
    ProviderErrorClass.INVALID_RESPONSE: "The AI model returned an unusable answer.",
    ProviderErrorClass.BLOCKED_URL: "The AI model address is not allowed.",
    ProviderErrorClass.HTTP_ERROR: "The AI model server reported an error.",
}


def _error(error_class: ProviderErrorClass) -> ProviderError:
    return ProviderError(error_class, _MESSAGES[error_class])


class OllamaProvider:
    """Structured extraction through a local Ollama server."""

    provider = "ollama"

    def __init__(
        self,
        client: GuardedHttpClient,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 180.0,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self.model = model
        self._timeout = timeout_seconds

    async def extract(self, request: ExtractionRequest) -> ProviderOutput:
        """Send the request and return the model's JSON text.

        Raises:
            ProviderError: unreachable, timeout, model missing, error status or unusable answer.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "stream": False,
            "format": request.json_schema,
            "think": False,
            "options": {
                "temperature": 0,
                "seed": 0,
                "num_ctx": _NUM_CTX,
                "num_predict": _NUM_PREDICT,
            },
        }
        started = time.monotonic()
        response = await self._call(
            self._client.post_json(f"{self._base_url}/api/chat", payload, timeout=self._timeout)
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        self._check_status(response)
        return ProviderOutput(content=self._content(response), latency_ms=latency_ms)

    async def available_models(self) -> list[str]:
        """Names of the models installed on the server (used to explain a missing model)."""
        response = await self._call(self._client.get(f"{self._base_url}/api/tags"))
        self._check_status(response)
        try:
            models = json.loads(response.body)["models"]
            return [str(item["name"]) for item in models]
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
        if response.status == 404:
            raise _error(ProviderErrorClass.MODEL_NOT_FOUND)
        if response.status != 200:
            raise _error(ProviderErrorClass.HTTP_ERROR)

    @staticmethod
    def _content(response: HttpResponse) -> str:
        try:
            content = json.loads(response.body)["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise _error(ProviderErrorClass.INVALID_RESPONSE) from exc
        if not isinstance(content, str):
            raise _error(ProviderErrorClass.INVALID_RESPONSE)
        return content


def build_ollama_provider(settings: Settings, *, model: str) -> OllamaProvider:
    """Create the provider with the URL policy of the deployment (ADR-035)."""
    host = urlsplit(settings.ollama_url).hostname or ""
    guard = UrlGuard(
        allow_private=settings.allow_local_providers,
        allowed_private_hosts=frozenset({host}) if host else frozenset(),
    )
    client = GuardedHttpClient(
        guard=guard,
        user_agent=f"JobsRadar/{__version__} (personal job-market radar)",
        total_timeout=float(settings.ollama_timeout_seconds),
    )
    return OllamaProvider(
        client,
        base_url=settings.ollama_url,
        model=model,
        timeout_seconds=float(settings.ollama_timeout_seconds),
    )


class OllamaEmbedder:
    """Text embeddings through a local Ollama server (``/api/embed``)."""

    provider = "ollama"

    def __init__(
        self,
        client: GuardedHttpClient,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self.model = model
        self._timeout = timeout_seconds

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` and return one vector each.

        Raises:
            ProviderError: unreachable, timeout, model missing, error status or unusable answer.
        """
        response = await OllamaProvider._call(
            self._client.post_json(
                f"{self._base_url}/api/embed",
                {"model": self.model, "input": texts, "truncate": True},
                timeout=self._timeout,
            )
        )
        OllamaProvider._check_status(response)
        try:
            vectors = json.loads(response.body)["embeddings"]
            result = [[float(x) for x in vector] for vector in vectors]
        except (ValueError, KeyError, TypeError) as exc:
            raise _error(ProviderErrorClass.INVALID_RESPONSE) from exc
        if len(result) != len(texts):
            raise _error(ProviderErrorClass.INVALID_RESPONSE)
        return result


def _guarded_client(settings: Settings) -> GuardedHttpClient:
    host = urlsplit(settings.ollama_url).hostname or ""
    guard = UrlGuard(
        allow_private=settings.allow_local_providers,
        allowed_private_hosts=frozenset({host}) if host else frozenset(),
    )
    return GuardedHttpClient(
        guard=guard,
        user_agent=f"JobsRadar/{__version__} (personal job-market radar)",
        total_timeout=float(settings.ollama_timeout_seconds),
    )


def build_ollama_embedder(settings: Settings, *, model: str | None = None) -> OllamaEmbedder:
    """Create the embedding provider with the URL policy of the deployment (ADR-035)."""
    return OllamaEmbedder(
        _guarded_client(settings),
        base_url=settings.ollama_url,
        model=model or settings.embedding_model,
        timeout_seconds=float(settings.ollama_timeout_seconds),
    )
