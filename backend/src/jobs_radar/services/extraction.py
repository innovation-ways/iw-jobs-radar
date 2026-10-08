"""Runs one AI extraction: prompt, provider call, validation, one repair, evidence and key checks.

Failure policy (document 13, section 6.2): an answer that cannot be used after one repair is
``invalid_output``; a provider that is unreachable, missing its model or refusing the address is an
*infrastructure* problem that leaves the job waiting without using an attempt; timeouts and
unusable provider answers use an attempt. The raw answer is never stored unvalidated.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from jobs_radar.adapters.providers.base import ExtractionProvider, ProviderError
from jobs_radar.domain.enums import ProviderErrorClass
from jobs_radar.schemas.extraction import ExtractionOutput
from jobs_radar.services.extraction_prompt import PreparedPrompt, build_prompt, build_repair
from jobs_radar.services.extraction_rules import (
    ParsedAnswer,
    find_contradictions,
    keep_known_keys,
    parse_lenient,
    verify_evidence,
)

# Provider failures that say nothing about the job: the job simply waits (no attempt is used).
_INFRASTRUCTURE = frozenset(
    {
        ProviderErrorClass.UNAVAILABLE,
        ProviderErrorClass.MODEL_NOT_FOUND,
        ProviderErrorClass.BLOCKED_URL,
        ProviderErrorClass.HTTP_ERROR,
    }
)
_PROBLEM_LIMIT = 800


class ExtractionError(Exception):
    """The extraction could not be produced. ``counts_as_attempt`` says whether the job used one."""

    def __init__(self, error_class: str, message: str, *, counts_as_attempt: bool) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.message = message
        self.counts_as_attempt = counts_as_attempt


@dataclass(frozen=True)
class ExtractionInput:
    """What the extractor is given about a job."""

    title: str
    description: str
    hints: Mapping[str, Sequence[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionResult:
    """A validated extraction with the checks that were applied to it."""

    output: ExtractionOutput
    unverified: list[str]
    dropped_keys: list[str]
    contradictions: list[dict[str, Any]]
    truncated: bool
    latency_ms: int

    def stored_attributes(self) -> dict[str, Any]:
        """Return the JSON stored in ``job_extraction.attributes_json``."""
        return {
            "output": self.output.model_dump(mode="json"),
            "unverified": self.unverified,
            "dropped_keys": self.dropped_keys,
            "contradictions": self.contradictions,
        }


def _problem(error: Exception) -> str:
    """Describe briefly and safely why an answer was unusable (field paths and rules only)."""
    if isinstance(error, ValidationError):
        lines = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()[:10]]
        return "; ".join(lines)[:_PROBLEM_LIMIT]
    return str(error)[:_PROBLEM_LIMIT]


class JobExtractor:
    """Extracts structured, evidence-checked attributes from a job posting."""

    def __init__(
        self,
        provider: ExtractionProvider,
        taxonomy: Mapping[str, set[str]],
        *,
        max_chars: int,
    ) -> None:
        self._provider = provider
        self._taxonomy = taxonomy
        self._max_chars = max_chars

    async def extract(self, job: ExtractionInput) -> ExtractionResult:
        """Extract ``job``'s attributes.

        Raises:
            ExtractionError: the provider failed or its answer stayed unusable after one repair.
        """
        prepared = build_prompt(
            title=job.title,
            description=job.description,
            hints=job.hints,
            taxonomy={kind: sorted(keys) for kind, keys in self._taxonomy.items()},
            max_chars=self._max_chars,
        )
        raw, latency = await self._call(prepared.request)
        try:
            parsed = parse_lenient(raw)
        except ValueError as first:
            repair = build_repair(prepared, previous=raw, problem=_problem(first))
            raw, repair_latency = await self._call(repair)
            latency += repair_latency
            try:
                parsed = parse_lenient(raw)
            except ValueError as second:
                msg = "The AI answer could not be used after one repair."
                raise ExtractionError("invalid_output", msg, counts_as_attempt=True) from second
        return self._checked(parsed, job, prepared, latency)

    async def _call(self, request: Any) -> tuple[str, int]:
        try:
            answer = await self._provider.extract(request)
        except ProviderError as error:
            raise ExtractionError(
                error.error_class.value,
                error.message,
                counts_as_attempt=error.error_class not in _INFRASTRUCTURE,
            ) from error
        return answer.content, answer.latency_ms

    def _checked(
        self,
        parsed: ParsedAnswer,
        job: ExtractionInput,
        prepared: PreparedPrompt,
        latency_ms: int,
    ) -> ExtractionResult:
        verified = verify_evidence(parsed.output, job.title, prepared.description_used)
        filtered = keep_known_keys(verified.output, self._taxonomy)
        return ExtractionResult(
            output=filtered.output,
            unverified=sorted({*parsed.notes, *verified.unverified}),
            dropped_keys=filtered.dropped,
            contradictions=find_contradictions(filtered.output, job.hints),
            truncated=prepared.truncated,
            latency_ms=latency_ms,
        )
