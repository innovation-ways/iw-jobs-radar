"""Judges how well one job fits one career direction with the local model (ADR-057, direction-v1).

The prompt holds the direction text the owner wrote and the job posting, nothing else: no profile,
no contact details. The model answers with a level and two verbatim quotes. Quotes are checked
here, as for extractions (ADR-044): a fit without a quote that really occurs in the posting becomes
``unknown``, and a direction quote that is not in the owner's text is dropped. Picking the best
direction among several is not done here; the matching engine does that deterministically.
"""

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from jobs_radar.adapters.providers.base import ExtractionProvider, ExtractionRequest, ProviderError
from jobs_radar.domain.directions import MAX_TEXT_CHARS
from jobs_radar.domain.enums import ProviderErrorClass
from jobs_radar.domain.text_match import quote_occurs, truncate_text

_LEVELS = ("strong", "partial", "weak", "none", "unknown")
_MAX_QUOTE_CHARS = 200
_PROBLEM_LIMIT = 400
# Provider failures that say nothing about the job: it simply waits (no attempt is used).
_INFRASTRUCTURE = frozenset(
    {
        ProviderErrorClass.UNAVAILABLE,
        ProviderErrorClass.MODEL_NOT_FOUND,
        ProviderErrorClass.BLOCKED_URL,
        ProviderErrorClass.HTTP_ERROR,
    }
)

SYSTEM_PROMPT = "\n".join(
    [
        "You judge how well one job posting fits one career direction that a person wrote in "
        "their own words. Answer with a JSON object only.",
        "",
        "Levels:",
        '- "strong": the posting is clearly the work, domain and kind of role the direction '
        "describes.",
        '- "partial": clearly related, but different in an important way (an adjacent role or '
        "domain, or only part of the direction).",
        '- "weak": only loosely related.',
        '- "none": unrelated to the direction, or against it.',
        '- "unknown": the posting does not say enough to tell.',
        "",
        "Rules:",
        "1. Use only what the posting states. Never guess.",
        '2. For "strong", "partial" and "weak", "job_quote" must be an exact quote copied '
        "verbatim from the posting title or description (at most 200 characters) that shows the "
        "fit. Never paraphrase, translate or invent a quote.",
        '3. "direction_quote" is an exact quote from the direction text (at most 200 characters) '
        "that the posting matches; null if none applies.",
        '4. For "none" and "unknown" the quotes may be null.',
        "5. Judge the fit of the work described, not whether the person would be hired.",
        "6. Answer with the JSON object only.",
    ]
)

_REPAIR_NOTE = (
    "Your previous answer was invalid: {problem}\n"
    "Previous answer (may be cut):\n{previous}\n\n"
    "Return the corrected JSON object only."
)
_PREVIOUS_LIMIT = 1500


@dataclass(frozen=True)
class DirectionTarget:
    """One career direction as the owner wrote it."""

    label: str
    text: str


@dataclass(frozen=True)
class DirectionOutcome:
    """A verified judgement, ready to store."""

    level: str
    job_quote: str | None
    direction_quote: str | None
    latency_ms: int


class DirectionError(Exception):
    """A judgement could not be produced; ``counts_as_attempt`` says if the job used an attempt."""

    def __init__(self, error_class: str, message: str, *, counts_as_attempt: bool) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.message = message
        self.counts_as_attempt = counts_as_attempt


class _Answer(BaseModel):
    """The model's answer; unknown extra keys are ignored, a bad level is refused."""

    model_config = ConfigDict(extra="ignore")

    level: Literal["strong", "partial", "weak", "none", "unknown"]
    job_quote: str | None = None
    direction_quote: str | None = None


def answer_schema() -> dict[str, Any]:
    """Return the JSON schema sent to the model (the quotes are bounded)."""
    quote = {"type": ["string", "null"], "maxLength": _MAX_QUOTE_CHARS}
    return {
        "type": "object",
        "properties": {
            "level": {"type": "string", "enum": list(_LEVELS)},
            "job_quote": quote,
            "direction_quote": quote,
        },
        "required": ["level"],
        "additionalProperties": False,
    }


def _problem(error: Exception) -> str:
    """Describe briefly why an answer was unusable (field paths and rules only)."""
    if isinstance(error, ValidationError):
        lines = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()[:5]]
        return "; ".join(lines)[:_PROBLEM_LIMIT]
    return str(error)[:_PROBLEM_LIMIT]


class DirectionJudge:
    """Judges a job posting against one career direction."""

    def __init__(self, provider: ExtractionProvider, *, max_chars: int) -> None:
        self._provider = provider
        self._max_chars = max_chars

    def _request(self, target: DirectionTarget, title: str, used: str) -> ExtractionRequest:
        user = (
            f"Career direction: {target.label}\n<<<\n{target.text[:MAX_TEXT_CHARS]}\n>>>\n\n"
            f"Job title: {title}\n\nPosting:\n<<<\n{used}\n>>>"
        )
        return ExtractionRequest(system=SYSTEM_PROMPT, user=user, json_schema=answer_schema())

    async def judge(
        self, target: DirectionTarget, *, title: str, description: str
    ) -> DirectionOutcome:
        """Return the verified judgement of ``target`` against the posting.

        Raises:
            DirectionError: the provider failed, or its answer stayed unusable after one repair.
        """
        used, _ = truncate_text(description, self._max_chars)
        request = self._request(target, title, used)
        raw, latency = await self._call(request)
        try:
            answer = self._parse(raw)
        except (ValueError, ValidationError) as first:
            repair = ExtractionRequest(
                system=request.system,
                user=request.user
                + "\n\n"
                + _REPAIR_NOTE.format(problem=_problem(first), previous=raw[:_PREVIOUS_LIMIT]),
                json_schema=request.json_schema,
            )
            raw, repair_latency = await self._call(repair)
            latency += repair_latency
            try:
                answer = self._parse(raw)
            except (ValueError, ValidationError) as second:
                msg = "The AI answer could not be used after one repair."
                raise DirectionError("invalid_output", msg, counts_as_attempt=True) from second
        return self._checked(answer, target, f"{title}\n{used}", latency)

    @staticmethod
    def _parse(raw: str) -> _Answer:
        data = json.loads(raw)
        if not isinstance(data, dict):
            msg = "The answer is not a JSON object."
            raise ValueError(msg)  # a ValueError is what the caller repairs
        return _Answer.model_validate(data)

    async def _call(self, request: ExtractionRequest) -> tuple[str, int]:
        try:
            output = await self._provider.extract(request)
        except ProviderError as error:
            raise DirectionError(
                error.error_class.value,
                error.message,
                counts_as_attempt=error.error_class not in _INFRASTRUCTURE,
            ) from error
        return output.content, output.latency_ms

    @staticmethod
    def _checked(
        answer: _Answer, target: DirectionTarget, job_text: str, latency_ms: int
    ) -> DirectionOutcome:
        """Apply the evidence rules: an unsupported fit is unknown, an unsupported quote goes."""
        job_quote = (answer.job_quote or "").strip()
        direction_quote = (answer.direction_quote or "").strip()
        in_job = bool(job_quote) and quote_occurs(job_quote, job_text)
        in_direction = bool(direction_quote) and quote_occurs(direction_quote, target.text)
        if answer.level in {"strong", "partial", "weak"} and not in_job:
            return DirectionOutcome("unknown", None, None, latency_ms)
        return DirectionOutcome(
            answer.level,
            job_quote if in_job else None,
            direction_quote if in_direction else None,
            latency_ms,
        )
