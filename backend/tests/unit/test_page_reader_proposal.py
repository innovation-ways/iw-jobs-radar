"""The model's reader proposal is checked on the page before the owner sees it (ADR-070)."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
import respx
from tests.job_board_support import build_ats, payload

from jobs_radar.adapters.providers.base import ExtractionRequest, ProviderError, ProviderOutput
from jobs_radar.adapters.sources.page_config import PageConfigAdapter, compact_html
from jobs_radar.core.errors import DependencyUnavailableError, InputValidationError
from jobs_radar.domain.enums import ProviderErrorClass
from jobs_radar.services.page_reader_proposal import PageReaderProposalService

ORIGIN = "https://careers.synthco.example"
LISTING = f"{ORIGIN}/careers"
GOOD = {
    "item_selector": "li.position",
    "title_selector": ".position-title",
    "link_selector": "a.position-link",
    "location_selector": ".position-place",
    "next_page_selector": "a.next",
}


class Chat:
    provider = "ollama"
    model = "qwen3:14b"

    def __init__(self, answer: Any = None, error: ProviderError | None = None) -> None:
        self.answer, self.error = answer, error
        self.requests: list[ExtractionRequest] = []

    async def extract(self, request: ExtractionRequest) -> ProviderOutput:
        self.requests.append(request)
        if self.error:
            raise self.error
        text = self.answer if isinstance(self.answer, str) else json.dumps(self.answer)
        return ProviderOutput(text, 3)


class Ai:
    def __init__(self, chat: Chat | None) -> None:
        self.chat = chat

    async def direction_target(self, owner_id: int) -> Any:
        if self.chat is None:
            return None
        return SimpleNamespace(provider_type="ollama"), self.chat


def service(chat: Chat | None) -> PageReaderProposalService:
    adapter: PageConfigAdapter = build_ats(PageConfigAdapter)
    return PageReaderProposalService(Ai(chat), adapter)


def serve_listing() -> None:
    respx.get(f"{ORIGIN}/robots.txt").respond(404)
    respx.get(LISTING).respond(200, content=payload("page_config", "listing.html"))


@respx.mock
async def test_a_good_proposal_is_verified_on_the_page_and_previewed() -> None:
    serve_listing()
    chat = Chat(GOOD)
    proposal = await service(chat).propose(1, LISTING)
    assert [p.title for p in proposal.preview] == ["Platform Engineer", "Data Analyst"]
    assert proposal.config.listing_url == LISTING  # the address is never the model's
    assert proposal.config.item_selector == "li.position"
    assert proposal.proposed_by.startswith("model:ollama:qwen3:14b")
    assert 'li class="position"' in chat.requests[0].user  # the outline carries the structure
    assert "var secret" not in chat.requests[0].user  # scripts never reach the model


@respx.mock
async def test_selectors_that_find_nothing_are_not_offered() -> None:
    serve_listing()
    with pytest.raises(DependencyUnavailableError) as caught:
        await service(Chat({**GOOD, "item_selector": "div.card"})).propose(1, LISTING)
    assert caught.value.details["error_class"] == "invalid_response"


@pytest.mark.parametrize(
    "answer",
    ["not json", "[]", {"item_selector": "li["}, {"item_selector": ""}, {"title_selector": "a"}],
)
@respx.mock
async def test_an_unusable_answer_is_reported_not_stored(answer: Any) -> None:
    serve_listing()
    with pytest.raises(DependencyUnavailableError):
        await service(Chat(answer)).propose(1, LISTING)


@respx.mock
async def test_a_provider_failure_is_reported_with_its_class() -> None:
    serve_listing()
    error = ProviderError(ProviderErrorClass.UNAVAILABLE, "The model is not reachable.")
    with pytest.raises(DependencyUnavailableError) as caught:
        await service(Chat(error=error)).propose(1, LISTING)
    assert caught.value.details["error_class"] == "unavailable"


async def test_without_a_local_model_nothing_is_read() -> None:
    with pytest.raises(InputValidationError):
        await service(None).propose(1, LISTING)


def test_the_outline_keeps_structure_and_cuts_repeated_blocks() -> None:
    items = "".join(f'<li class="p"><a href="/j/{n}">Role {n}</a></li>' for n in range(20))
    outline = compact_html(f"<html><body><ul>{items}</ul><script>x()</script></body></html>")
    assert outline.count('class="p"') == 3
    assert "x()" not in outline
    assert len(compact_html("<body>" + "word " * 20000 + "</body>", limit=500)) <= 500
