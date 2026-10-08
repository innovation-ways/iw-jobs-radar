"""A scriptable AI provider for tests: no model, no network, fully deterministic."""

import json
from collections.abc import Callable
from typing import Any

from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderError, ProviderOutput


class FakeProvider:
    """Returns scripted answers, one per call. A ``ProviderError`` in the script is raised.

    ``responder`` computes the answer from the request instead (it may return a dict, a string or
    raise). Every request is recorded in ``requests`` so tests can inspect the prompt.
    """

    provider = "fixture"

    def __init__(
        self,
        script: list[object] | None = None,
        *,
        model: str = "fixture-model",
        responder: Callable[[ExtractionRequest], object] | None = None,
    ) -> None:
        self.model = model
        self.script = list(script or [])
        self.responder = responder
        self.requests: list[ExtractionRequest] = []

    async def extract(self, request: ExtractionRequest) -> ProviderOutput:
        self.requests.append(request)
        item: Any = self.responder(request) if self.responder else self.script.pop(0)
        if isinstance(item, ProviderError):
            raise item
        if isinstance(item, Exception):
            raise item
        text = item if isinstance(item, str) else json.dumps(item)
        return ProviderOutput(content=text, latency_ms=7)
