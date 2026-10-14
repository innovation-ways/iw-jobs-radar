"""The ``extract-v4`` prompt (document 13, section 6.1; ADR-027, ADR-073).

The prompt is built from the job alone: it never receives a profile or an intent, so one
extraction serves every intent. The model is told to extract only what the posting states, to
quote its evidence verbatim, and to answer with a JSON object that follows the output contract.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from jobs_radar.adapters.providers.base import ExtractionRequest
from jobs_radar.domain.text_match import truncate_text
from jobs_radar.schemas.extraction import ExtractionOutput

SYSTEM_PROMPT = "\n".join(
    [
        "You extract structured facts from one job posting and answer with a JSON object.",
        "",
        "Rules:",
        "1. Use only what the posting states. Never guess. If an attribute is not stated, set its "
        'status to "unknown", its value to null, its confidence to 0 and its evidence to null.',
        '2. For every known attribute give "evidence": an exact quote copied verbatim from the '
        "posting title or description (at most 200 characters). Never paraphrase, translate or "
        "invent a quote.",
        '3. "confidence" is a number from 0 to 1.',
        "4. For role families, sectors, seniority, employment types, employer type and benefits, "
        "use only the allowed keys listed in the message. If none fits, leave the attribute "
        "unknown.",
        "5. Compensation exactly as stated: form (annual_salary, day_rate or hourly_rate), ISO "
        "currency code, min, max (equal when one figure is given) and period (year, month, day "
        "or hour). Do not convert.",
        "6. work_mode is remote, hybrid or onsite. remote_regions lists the regions or countries "
        "remote work is open to (for example EU, UK, PT, WORLD); locations lists the places named "
        "for the job.",
        '7. skills lists technologies and skills the posting asks for with importance "must" '
        '(required) or "nice" (preferred), named as written, at most 25.',
        "8. role_families: list the one to three families that best fit the role, each with a "
        "quote "
        "from the posting describing the work. Leave it empty only if no role is described.",
        "9. The evidence is always text from the posting, never the value or a key. For example, "
        'for the posting text "Fully remote within the EU." the answer is {"value": "remote", '
        '"status": "known", "confidence": 0.95, "evidence": "Fully remote within the EU"}; for an '
        'attribute the posting never mentions it is {"value": null, "status": "unknown", '
        '"confidence": 0, "evidence": null}.',
        "10. employment_types: tell the kinds of work contract apart. employee_permanent is a "
        "permanent employment contract. employee_fixed_term is a fixed-term or temporary "
        "employment contract. contractor_b2b is a self-employed contractor invoicing through "
        "their own company (B2B, limited company, sole trader). freelance is an independent "
        "freelancer or project-based self-employed work. contractor_agency is a contract placed "
        "through a recruitment agency or umbrella company, paid by day or hour. A day rate or an "
        "hourly rate with no mention of employment is a contractor kind, not employee_permanent.",
        "11. Answer with the JSON object only.",
    ]
)

# Limits written into the schema sent to the model. Without them a small model can fall into a loop
# (the same list item hundreds of times) until its output budget runs out and the JSON is cut off.
# They repeat what the prompt already asks for; the validation model itself is not tightened, so
# stored extractions keep validating.
_MAX_SKILLS = 25  # rule 7
_MAX_ROLE_FAMILIES = 3  # rule 8
_MAX_LIST_ITEMS = 12  # any other list: regions, locations, languages, keys
_MAX_QUOTE_CHARS = 200  # rule 2


def bounded_schema() -> dict[str, Any]:
    """Return the output schema with a maximum size for every list and every quote."""
    schema = ExtractionOutput.model_json_schema()

    def bound(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "array":
                node.setdefault("maxItems", _MAX_LIST_ITEMS)
            quote = node.get("evidence")
            if isinstance(quote, dict):
                for variant in quote.get("anyOf") or [quote]:
                    if variant.get("type") == "string":
                        variant["maxLength"] = _MAX_QUOTE_CHARS
            for value in node.values():
                bound(value)
        elif isinstance(node, list):
            for value in node:
                bound(value)

    bound(schema)
    # The lists have defaults in the validation model (so stored extractions keep validating), but
    # a schema without them in `required` lets the model skip them: about a third of the answers
    # had no role family. Requiring them forces the model to answer; an empty list is still valid.
    schema["required"] = [*schema["required"], "role_families", "skills"]
    schema["properties"]["skills"]["maxItems"] = _MAX_SKILLS
    schema["properties"]["role_families"]["maxItems"] = _MAX_ROLE_FAMILIES
    return schema


_REPAIR_NOTE = (
    "Your previous answer was invalid: {problem}\n"
    "Previous answer (may be cut):\n{previous}\n\n"
    "Return the corrected JSON object only."
)
_PREVIOUS_LIMIT = 4000


@dataclass(frozen=True)
class PreparedPrompt:
    """A request ready for a provider, with what was actually sent."""

    request: ExtractionRequest
    description_used: str
    truncated: bool


def build_prompt(
    *,
    title: str,
    description: str,
    hints: Mapping[str, Sequence[str]],
    taxonomy: Mapping[str, Sequence[str]],
    max_chars: int,
) -> PreparedPrompt:
    """Build the ``extract-v4`` request for one job (no profile or intent data is accepted)."""
    used, truncated = truncate_text(description, max_chars)
    allowed = "\n".join(f"- {kind}: {', '.join(keys)}" for kind, keys in sorted(taxonomy.items()))
    parts = [f"Title: {title}"]
    shown_hints = {key: list(values) for key, values in hints.items() if values}
    if shown_hints:
        parts.append(
            "Source hints (structured fields from the job board; they may be wrong, confirm or "
            f"contradict them from the text):\n{json.dumps(shown_hints, ensure_ascii=False)}"
        )
    parts.append(f"Allowed keys:\n{allowed}")
    parts.append(f"Posting:\n<<<\n{used}\n>>>")
    request = ExtractionRequest(
        system=SYSTEM_PROMPT,
        user="\n\n".join(parts),
        json_schema=bounded_schema(),
    )
    return PreparedPrompt(request, used, truncated)


def build_repair(prepared: PreparedPrompt, *, previous: str, problem: str) -> ExtractionRequest:
    """Return the one repair request: the same posting plus what was wrong with the last answer."""
    note = _REPAIR_NOTE.format(problem=problem, previous=previous[:_PREVIOUS_LIMIT])
    return ExtractionRequest(
        system=prepared.request.system,
        user=f"{prepared.request.user}\n\n{note}",
        json_schema=prepared.request.json_schema,
    )
