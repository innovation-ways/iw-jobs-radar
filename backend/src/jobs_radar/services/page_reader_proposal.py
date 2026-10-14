"""The local model proposes how to read a company's careers page (ADR-070 layer 3).

Only for a server-rendered page that has neither a known ATS nor structured postings. The page's
outline goes to the *local* model (ADR-046: never a remote one, no fallback), which answers with CSS
selectors, never code. The proposal is checked by the same fixed reader that will run later: it must
find at least one posting on the page, and the owner sees what it found before approving. Nothing is
stored here.
"""

import json
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderError
from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.adapters.sources.page_config import (
    ListedPosting,
    PageConfigAdapter,
    compact_html,
    extract_listing,
)
from jobs_radar.core.errors import DependencyUnavailableError, InputValidationError
from jobs_radar.domain.careers_markers import page_identifier
from jobs_radar.schemas.page_reader import PageReaderConfig
from jobs_radar.services.sources import translate_source_error

PROMPT_VERSION = "reader-v1"
PREVIEW_LIMIT = 10
SYSTEM_PROMPT = "\n".join(
    [
        "You configure a fixed reader for a company's careers page. You receive a simplified "
        "outline of the page's HTML (only class, id and href attributes, shortened texts, repeated "
        "blocks cut to a few). Answer with CSS selectors that a program will apply; never write "
        "code.",
        '"item_selector": matches EVERY job posting block of the listing, one element per posting '
        "(for example a list item or card that contains the posting's title and link). It must not "
        "match menus, filters, headings or other page parts.",
        '"title_selector": inside one posting block, the element holding the job title.',
        '"link_selector": inside one posting block, the link (a[href]) to the posting. Use an '
        "empty string if the block itself is the link.",
        '"location_selector": inside one posting block, the element holding the place, or an empty '
        "string if the page shows none.",
        '"next_page_selector": the link to the next page of the listing, or an empty string if '
        "there is no paging in the outline.",
        "Use only classes, ids and tags you can see in the outline. If the outline holds no job "
        'postings at all, answer with an empty "item_selector".',
    ]
)
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "item_selector": {"type": "string"},
        "title_selector": {"type": "string"},
        "link_selector": {"type": "string"},
        "location_selector": {"type": "string"},
        "next_page_selector": {"type": "string"},
    },
    "required": ["item_selector", "title_selector", "link_selector"],
}


class ModelTarget(Protocol):
    """Where the local model is chosen (the AI & privacy settings)."""

    async def direction_target(self, owner_id: int) -> Any:
        """Return ``(connection, provider)`` of the local job model, or ``None``."""
        ...


@dataclass(frozen=True)
class ReaderProposal:
    """A proposed reader with the postings it finds on the first listing page."""

    config: PageReaderConfig
    preview: tuple[ListedPosting, ...]
    proposed_by: str


def _invalid() -> DependencyUnavailableError:
    return DependencyUnavailableError(
        "The model did not give a reader that finds the postings on this page.",
        details={"error_class": "invalid_response"},
    )


class PageReaderProposalService:
    """Builds a reader proposal for one careers page."""

    def __init__(self, ai: ModelTarget, adapter: PageConfigAdapter) -> None:
        self._ai = ai
        self._adapter = adapter

    async def propose(self, owner_id: int, careers_url: str) -> ReaderProposal:
        """Read the careers page, ask the local model and verify its answer on the page.

        Raises:
            InputValidationError: no local model is chosen, or the page cannot be read at all.
            DependencyUnavailableError: the model failed or its answer finds no posting.
        """
        target = await self._ai.direction_target(owner_id)
        if target is None:
            msg = "Choose a local model for job analysis in AI & privacy to propose a reader."
            raise InputValidationError(msg)
        connection, provider = target
        identifier = page_identifier(careers_url)
        try:
            html = await self._adapter.fetch_page(careers_url, key=identifier)
        except SourceError as error:
            raise translate_source_error(error) from error
        user = f"Careers page: {careers_url}\n\nOUTLINE\n{compact_html(html)}"
        try:
            output = await provider.extract(
                ExtractionRequest(system=SYSTEM_PROMPT, user=user, json_schema=_SCHEMA)
            )
        except ProviderError as error:
            raise DependencyUnavailableError(
                error.message, details={"error_class": error.error_class.value}
            ) from error
        config = self._config(output.content, careers_url)
        postings, _ = extract_listing(config, html, careers_url)
        if not postings:
            raise _invalid()
        return ReaderProposal(
            config,
            tuple(postings[:PREVIEW_LIMIT]),
            f"model:{connection.provider_type}:{provider.model}:{PROMPT_VERSION}"[:120],
        )

    @staticmethod
    def _config(answer: str, careers_url: str) -> PageReaderConfig:
        """Turn the model's answer into a configuration; the address is never the model's."""
        try:
            data = json.loads(answer)
        except ValueError as error:
            raise _invalid() from error
        if not isinstance(data, dict):
            raise _invalid()

        def text(key: str) -> str | None:
            value = data.get(key)
            return value.strip() if isinstance(value, str) and value.strip() else None

        try:
            return PageReaderConfig(
                listing_url=careers_url,
                item_selector=text("item_selector") or "",
                title_selector=text("title_selector"),
                link_selector=text("link_selector"),
                location_selector=text("location_selector"),
                next_page_selector=text("next_page_selector"),
            )
        except ValidationError as error:
            raise _invalid() from error
