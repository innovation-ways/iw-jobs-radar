"""Build a provider adapter from a connection's settings (ADR-035).

The service turns a stored connection into a :class:`ProviderSpec` (the decrypted key included) and
the factory creates the adapter. Adapters never see the database; the spec is the only hand-over.
"""

from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

from jobs_radar import __version__
from jobs_radar.adapters.providers.base import ExtractionProvider
from jobs_radar.adapters.providers.ollama import OllamaProvider
from jobs_radar.adapters.providers.openai_compatible import OpenAiCompatibleProvider
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.core.settings import Settings
from jobs_radar.core.url_guard import UrlGuard


@dataclass(frozen=True)
class ProviderSpec:
    """What is needed to talk to one provider. The key is excluded from ``repr``."""

    provider_type: str
    base_url: str
    model: str
    api_key: str | None = field(default=None, repr=False)


class ModelLister(Protocol):
    """A provider that can also say which models it offers."""

    async def available_models(self) -> list[str]:
        """Return the model ids offered by the provider."""
        ...


class ListingProvider(ExtractionProvider, ModelLister, Protocol):
    """An extraction provider that can list its models."""


def build_provider(
    spec: ProviderSpec, settings: Settings
) -> OllamaProvider | OpenAiCompatibleProvider:
    """Create the adapter for ``spec`` with the URL policy of the deployment."""
    agent = f"JobsRadar/{__version__} (personal job-market radar)"
    if spec.provider_type == "ollama":
        host = urlsplit(spec.base_url).hostname or ""
        guard = UrlGuard(
            allow_private=settings.allow_local_providers,
            allowed_private_hosts=frozenset({host}) if host else frozenset(),
        )
        client = GuardedHttpClient(
            guard=guard, user_agent=agent, total_timeout=float(settings.ollama_timeout_seconds)
        )
        return OllamaProvider(
            client,
            base_url=spec.base_url,
            model=spec.model,
            timeout_seconds=float(settings.ollama_timeout_seconds),
        )
    client = GuardedHttpClient(guard=UrlGuard(), user_agent=agent, total_timeout=120.0)
    return OpenAiCompatibleProvider(
        client,
        base_url=spec.base_url,
        model=spec.model,
        api_key=spec.api_key or "",
        provider=spec.provider_type,
    )
