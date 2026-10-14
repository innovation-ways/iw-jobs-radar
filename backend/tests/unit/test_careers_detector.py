"""Detecting how a company's careers page can be collected (ADR-070.2), with no network."""

from typing import Any

import httpx
import pytest
import respx

from jobs_radar.adapters.sources.base import BoardInfo, SourceError
from jobs_radar.adapters.sources.detector import CareersDetector, Detection, DetectionOutcome
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.core.url_guard import UrlGuard
from jobs_radar.domain.enums import SourceErrorClass, SourceType

CAREERS = "https://careers.synthco.example/"
WEBSITE = "https://www.synthco.example/"


class FakeBoard:
    """An adapter whose ``validate`` answers from a table: the known boards exist, others do not."""

    def __init__(self, source_type: SourceType, boards: dict[str, BoardInfo]) -> None:
        self.source_type = source_type
        self._boards = boards
        self.validated: list[str] = []

    def endpoint(self, identifier: str) -> str:  # pragma: no cover - not used by the detector
        return identifier

    async def validate(self, identifier: str, *args: Any, **kwargs: Any) -> BoardInfo:
        self.validated.append(identifier)
        if identifier not in self._boards:
            raise SourceError(SourceErrorClass.NOT_FOUND, "The board was not found.")
        return self._boards[identifier]

    async def collect(self, checkpoint: Any) -> Any:  # pragma: no cover - not used
        raise AssertionError


def detector(**boards: dict[str, BoardInfo]) -> tuple[CareersDetector, dict[SourceType, FakeBoard]]:
    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    client = GuardedHttpClient(guard=UrlGuard(resolver=resolve), user_agent="JobsRadar/test")
    adapters = {
        SourceType(name): FakeBoard(SourceType(name), found) for name, found in boards.items()
    }
    return CareersDetector(client, adapters), adapters  # type: ignore[arg-type]


def page(html: str, *, url: str = CAREERS, status: int = 200) -> respx.Route:
    return respx.get(url).respond(status, html=html)


def no_robots(origin: str = "https://careers.synthco.example") -> None:
    respx.get(f"{origin}/robots.txt").respond(404)


@respx.mock
async def test_a_board_address_is_resolved_without_reading_any_page() -> None:
    sut, adapters = detector(ashby={"mistral.ai": BoardInfo("Mistral AI", 213)})
    result = await sut.detect("https://jobs.ashbyhq.com/mistral.ai")
    assert result.outcome is DetectionOutcome.DETECTED
    (candidate,) = result.candidates
    assert (candidate.source_type, candidate.identifier) == (SourceType.ASHBY, "mistral.ai")
    assert candidate.postings_count == 213
    assert candidate.layer == "ats"
    assert len(respx.calls) == 0
    assert adapters[SourceType.ASHBY].validated == ["mistral.ai"]


@respx.mock
async def test_an_embedded_board_is_found_in_the_careers_page() -> None:
    no_robots()
    page('<script src="https://boards.greenhouse.io/embed/job_board/js?for=synthco"></script>')
    sut, _ = detector(greenhouse={"synthco": BoardInfo("Synthco", 12)})
    result = await sut.detect(CAREERS)
    assert result.outcome is DetectionOutcome.DETECTED
    assert [c.identifier for c in result.candidates] == ["synthco"]


@respx.mock
async def test_a_redirect_to_a_board_is_followed_and_recognised() -> None:
    no_robots()
    respx.get(CAREERS).respond(302, headers={"location": "https://jobs.lever.co/synthco"})
    respx.get("https://jobs.lever.co/synthco").respond(200, html="<html>board</html>")
    sut, _ = detector(lever={"synthco": BoardInfo("Synthco", 3)})
    result = await sut.detect(CAREERS)
    assert result.outcome is DetectionOutcome.DETECTED
    assert result.candidates[0].source_type is SourceType.LEVER


@respx.mock
async def test_several_boards_are_ambiguous_and_only_real_ones_are_offered() -> None:
    no_robots()
    page(
        '<a href="https://boards.greenhouse.io/synthco">A</a>'
        '<a href="https://jobs.lever.co/synthco-labs">B</a>'
        '<a href="https://jobs.ashbyhq.com/ghost">C</a>'
    )
    sut, _ = detector(
        greenhouse={"synthco": BoardInfo("Synthco", 41)},
        lever={"synthco-labs": BoardInfo("Synthco Labs", 6)},
        ashby={},
    )
    result = await sut.detect(CAREERS)
    assert result.outcome is DetectionOutcome.AMBIGUOUS
    assert [c.identifier for c in result.candidates] == ["synthco", "synthco-labs"]


@respx.mock
async def test_markers_that_do_not_validate_are_unsupported_not_a_wrong_source() -> None:
    no_robots()
    page('<a href="https://jobs.ashbyhq.com/ghost">C</a>')
    sut, _ = detector(ashby={})
    result = await sut.detect(CAREERS)
    assert result.outcome is DetectionOutcome.UNSUPPORTED
    assert result.candidates == ()


@respx.mock
async def test_a_page_with_posting_links_and_no_known_system_is_unsupported() -> None:
    no_robots()
    page('<a href="/jobs/senior-engineer-1">Senior engineer</a>' + "<p>" + "text " * 80 + "</p>")
    sut, _ = detector()
    result = await sut.detect(CAREERS)
    assert result.outcome is DetectionOutcome.UNSUPPORTED
    assert result.reason


@respx.mock
async def test_an_application_shell_is_script_only() -> None:
    no_robots()
    page('<html><body><div id="__nuxt"></div><script src="/a.js"></script></body></html>')
    sut, _ = detector()
    result = await sut.detect(CAREERS)
    assert result.outcome is DetectionOutcome.SCRIPT_ONLY


@respx.mock
async def test_robots_txt_that_forbids_the_page_blocks_it_without_requesting_the_page() -> None:
    respx.get("https://careers.synthco.example/robots.txt").respond(
        200, text="User-agent: *\nDisallow: /\n"
    )
    route = page("<html></html>")
    sut, _ = detector()
    result = await sut.detect(CAREERS)
    assert result.outcome is DetectionOutcome.BLOCKED
    assert not route.called


@pytest.mark.parametrize("status", [401, 403, 429])
@respx.mock
async def test_a_refusing_site_is_blocked(status: int) -> None:
    no_robots()
    page("denied", status=status)
    sut, _ = detector()
    assert (await sut.detect(CAREERS)).outcome is DetectionOutcome.BLOCKED


@respx.mock
async def test_a_server_error_or_a_timeout_is_unreachable() -> None:
    no_robots()
    page("boom", status=503)
    sut, _ = detector()
    assert (await sut.detect(CAREERS)).outcome is DetectionOutcome.UNREACHABLE
    respx.get(CAREERS).mock(side_effect=httpx.ConnectTimeout("slow"))
    assert (await sut.detect(CAREERS)).outcome is DetectionOutcome.UNREACHABLE


@respx.mock
async def test_a_redirect_to_an_unrelated_site_is_not_read() -> None:
    no_robots()
    respx.get(CAREERS).respond(302, headers={"location": "https://other.example/jobs"})
    other = respx.get("https://other.example/jobs").respond(
        200, html='<a href="https://jobs.lever.co/other">x</a>'
    )
    sut, adapters = detector(lever={"other": BoardInfo("Other", 1)})
    result = await sut.detect(CAREERS, website_url=WEBSITE)
    assert result.outcome is DetectionOutcome.UNSUPPORTED
    assert "another site" in (result.reason or "")
    assert other.called  # the redirect was followed once, to know where it went ...
    assert adapters[SourceType.LEVER].validated == []  # ... but nothing in it was trusted


@respx.mock
async def test_eightfold_is_probed_only_when_the_page_shows_its_assets() -> None:
    no_robots("https://jobs.synthco.example")
    respx.get("https://jobs.synthco.example/").respond(
        200, html='<script src="https://static.vscdn.net/app.js"></script>'
    )
    sut, adapters = detector(eightfold={"jobs.synthco.example": BoardInfo("Synthco", 30)})
    result = await sut.detect("https://jobs.synthco.example/")
    assert result.outcome is DetectionOutcome.DETECTED
    assert result.candidates[0].source_type is SourceType.EIGHTFOLD
    assert adapters[SourceType.EIGHTFOLD].validated == ["jobs.synthco.example"]

    respx.get("https://jobs.synthco.example/").respond(200, html="<html>plain</html>")
    sut, adapters = detector(eightfold={"jobs.synthco.example": BoardInfo("Synthco", 30)})
    await sut.detect("https://jobs.synthco.example/")
    assert adapters[SourceType.EIGHTFOLD].validated == []


@respx.mock
async def test_at_most_three_boards_are_validated() -> None:
    no_robots()
    links = "".join(f'<a href="https://jobs.lever.co/co{n}">x</a>' for n in range(6))
    page(links)
    sut, adapters = detector(lever={f"co{n}": BoardInfo(f"Co {n}", 1) for n in range(6)})
    result = await sut.detect(CAREERS)
    assert len(adapters[SourceType.LEVER].validated) == 3
    assert len(result.candidates) == 3


def test_detection_is_a_plain_value() -> None:
    assert Detection(DetectionOutcome.UNSUPPORTED, (), "why").candidates == ()
