"""Contract between the extraction service and an AI provider (HLD section 6, ADR-021, ADR-027).

A provider is pure transport: it sends a prompt and a JSON schema to a model and returns the raw
text. Building prompts, validating the answer and checking evidence belong to the service, so
swapping the provider never changes what is stored or scored. Providers never see profiles or
repositories, and their errors never contain prompts or job text.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from jobs_radar.domain.enums import ProviderErrorClass


class ProviderError(Exception):
    """An AI provider call failed. ``error_class`` is a stable reason; the message is generic."""

    def __init__(self, error_class: ProviderErrorClass, message: str) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.message = message


@dataclass(frozen=True)
class ExtractionRequest:
    """One structured-output request."""

    system: str
    user: str
    json_schema: Mapping[str, Any]


@dataclass(frozen=True)
class ProviderOutput:
    """The model's raw answer (JSON text, not yet validated) and how long the call took."""

    content: str
    latency_ms: int


class ExtractionProvider(Protocol):
    """A model that turns a prompt into JSON text constrained by a schema."""

    provider: str
    model: str

    async def extract(self, request: ExtractionRequest) -> ProviderOutput:
        """Run the request. Raises :class:`ProviderError`."""
        ...
