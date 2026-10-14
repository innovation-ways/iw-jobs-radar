"""A company's own careers page, read with a configuration the owner approved (ADR-070 layer 3).

For a server-rendered page that has neither a known ATS nor structured data, the local model may
propose a :class:`PageReaderConfig` and the owner approves it after seeing a preview. This module
is the fixed reader that executes it: it applies CSS selectors to the listing page (following the
"next" link up to ``max_pages``) and, optionally, to each posting page. No AI and no code from the
configuration run here. Only pages of the company's own registered domain are read, ``robots.txt``
is honoured, requests are spaced, and a run reads at most ``MAX_DETAIL_PAGES`` posting pages (the
rest makes it ``partial``, which never closes postings). A page that no longer yields any posting
fails visibly as ``schema_changed``.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from jobs_radar.adapters.enrichment.website import page_text
from jobs_radar.adapters.sources.base import (
    BoardInfo,
    CollectionResult,
    RateLimiter,
    SourceCheckpoint,
    SourceError,
    SourcePosting,
)
from jobs_radar.adapters.sources.company_board import clean, guess_company_name
from jobs_radar.adapters.sources.polite_http import PoliteGetter
from jobs_radar.adapters.sources.robots import RobotsGate
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.domain.careers_markers import page_address
from jobs_radar.domain.domains import registered_domain
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.page_reader import PageReaderConfig
from jobs_radar.schemas.source_filters import JobBoardFilters

MAX_DETAIL_PAGES = 100
_MAX_PAGE_BYTES = 3_000_000
_DESCRIPTION_LIMIT = 20_000
_HEADERS = {"Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"}


@dataclass(frozen=True)
class ListedPosting:
    """One posting block read from a listing page."""

    title: str
    url: str
    location: str


def _first_text(block: Tag, selector: str | None) -> str:
    if not selector:
        return clean(block.get_text(" ", strip=True))
    found = block.select_one(selector)
    return clean(found.get_text(" ", strip=True)) if found is not None else ""


def _link(block: Tag, selector: str | None) -> str:
    target: Tag | None
    if selector:
        target = block.select_one(selector)
    else:
        target = block if block.name == "a" else block.find("a", href=True)
    if target is None:
        return ""
    if target.name != "a" and not target.get("href"):
        target = target.find("a", href=True) or target
    href = target.get("href")
    return href.strip() if isinstance(href, str) else ""


def extract_listing(
    config: PageReaderConfig, html: str, page_url: str
) -> tuple[list[ListedPosting], str | None]:
    """Apply a configuration to one listing page.

    Returns the postings (title and address both present, on the page's registered domain, in page
    order, repeated addresses dropped) and the address of the next listing page, if any.
    """
    soup = BeautifulSoup(html, "lxml")
    domain = registered_domain(page_url)
    seen: set[str] = set()
    postings: list[ListedPosting] = []
    for block in soup.select(config.item_selector):
        if not isinstance(block, Tag):
            continue
        href = _link(block, config.link_selector)
        url = urldefrag(urljoin(page_url, href))[0] if href else ""
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or registered_domain(url) != domain:
            continue
        title = _first_text(block, config.title_selector)
        if not title or url in seen:
            continue
        seen.add(url)
        place = _first_text(block, config.location_selector) if config.location_selector else ""
        postings.append(ListedPosting(title, url, place))
    next_url: str | None = None
    if config.next_page_selector:
        nxt = soup.select_one(config.next_page_selector)
        target = nxt.get("href") if isinstance(nxt, Tag) else None
        if isinstance(target, str) and target.strip():
            candidate = urldefrag(urljoin(page_url, target.strip()))[0]
            if registered_domain(candidate) == domain and candidate != page_url:
                next_url = candidate
    return postings, next_url


def extract_description(config: PageReaderConfig, html: str) -> str:
    """Return the posting text of a detail page: the configured block, else the readable text."""
    if config.description_selector:
        soup = BeautifulSoup(html, "lxml")
        found = soup.select_one(config.description_selector)
        if found is not None:
            lines = [clean(line) for line in found.get_text("\n").splitlines()]
            text = "\n".join(line for line in lines if line)
            if text:
                return text[:_DESCRIPTION_LIMIT]
    return page_text(html)[:_DESCRIPTION_LIMIT]


class PageConfigAdapter:
    """Collects a careers page through an approved reader configuration."""

    source_type = SourceType.PAGE_CONFIG

    def __init__(
        self,
        client: GuardedHttpClient,
        *,
        sleep: Any = asyncio.sleep,
        limiter: RateLimiter | None = None,
        clock: Any = None,
    ) -> None:
        self._client = client
        self._getter = PoliteGetter(
            client,
            sleep=sleep,
            limiter=limiter,
            not_found_message="The careers page was not found.",
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    def endpoint(self, identifier: str) -> str:
        """Return the careers address stored in the source configuration."""
        return page_address(identifier)

    async def fetch_page(self, url: str, *, key: str, per_minute: int = 6) -> str:
        """Read one page of the company's own site (``robots.txt`` honoured).

        Raises:
            SourceError: robots.txt forbids it, it is missing, too large or otherwise unreadable.
        """
        gate = RobotsGate(self._client)
        if not await gate.allowed(url):
            msg = "The site's robots.txt does not allow automated reading of this page."
            raise SourceError(SourceErrorClass.CONFIGURATION, msg)
        return await self._read(url, key, per_minute)

    async def _read(self, url: str, key: str, per_minute: int) -> str:
        response = await self._getter.get(url, _HEADERS, key, per_minute=per_minute)
        if len(response.body) > _MAX_PAGE_BYTES:
            raise SourceError(SourceErrorClass.TOO_LARGE, "A page of the site is too large.")
        return response.body.decode("utf-8", "replace")

    async def preview(
        self, config: PageReaderConfig, *, key: str, per_minute: int = 6
    ) -> list[ListedPosting]:
        """Return the postings a configuration finds on its listing pages (the owner's preview)."""
        gate = RobotsGate(self._client)
        found: list[ListedPosting] = []
        known: set[str] = set()
        visited: set[str] = set()
        current: str | None = config.listing_url
        for _ in range(config.max_pages):
            if current is None or current in visited:
                break
            visited.add(current)
            if not await gate.allowed(current):
                msg = "The site's robots.txt does not allow automated reading of this page."
                raise SourceError(SourceErrorClass.CONFIGURATION, msg)
            page_postings, current = extract_listing(
                config, await self._read(current, key, per_minute), current
            )
            for posting in page_postings:
                if posting.url not in known:
                    known.add(posting.url)
                    found.append(posting)
        return found

    async def validate(
        self,
        identifier: str,
        credential: str | None = None,
        filters: JobBoardFilters | None = None,
        scope: LocationScope | None = None,
    ) -> BoardInfo:
        """Refuse: a careers-page reader is validated with its configuration, not an identifier."""
        msg = "A careers-page reader needs its approved configuration."
        raise SourceError(SourceErrorClass.CONFIGURATION, msg)

    async def collect(self, checkpoint: SourceCheckpoint) -> CollectionResult:
        """Read the listing (and posting pages) with the approved configuration."""
        started = asyncio.get_running_loop().time()
        if not checkpoint.page_config:
            msg = "This careers page has no approved reader."
            raise SourceError(SourceErrorClass.CONFIGURATION, msg)
        config = PageReaderConfig.model_validate(checkpoint.page_config)
        key, per_minute = checkpoint.identifier, checkpoint.rate_limit_per_minute
        listed = await self.preview(config, key=key, per_minute=per_minute)
        if not listed:
            msg = "The careers page no longer matches the approved reader (schema_changed)."
            raise SourceError(SourceErrorClass.SCHEMA_CHANGED, msg)

        gate = RobotsGate(self._client)
        postings: list[SourcePosting] = []
        incomplete = False
        details = 0
        for item in listed:
            description = item.title
            if config.fetch_detail:
                if details >= MAX_DETAIL_PAGES and not checkpoint.backlog:
                    incomplete = True
                    continue
                details += 1
                try:
                    if not await gate.allowed(item.url):
                        continue
                    description = extract_description(
                        config, await self._read(item.url, key, per_minute)
                    )
                except SourceError as error:
                    if error.error_class is not SourceErrorClass.NOT_FOUND:
                        incomplete = True  # could not be read: nothing may be closed on this run
                    continue
            postings.append(
                SourcePosting(
                    external_job_id=item.url,
                    title=item.title,
                    source_url=item.url,
                    apply_url=item.url,
                    description_text=description,
                    locations=(item.location,) if item.location else (),
                    posted_at=None,
                    source_updated_at=None,
                    departments=(),
                    language=None,
                    raw_payload={"title": item.title, "url": item.url, "location": item.location},
                )
            )
        duration = int((asyncio.get_running_loop().time() - started) * 1000)
        return CollectionResult(
            "modified",
            tuple(postings),
            None,
            200,
            duration,
            len(listed),
            dropped_count=len(listed) - len(postings),
            truncated=incomplete,
        )


def company_label(identifier: str) -> str:
    """Return a readable company name guessed from a careers-page identifier."""
    host = identifier.split("/")[0]
    domain = registered_domain(f"https://{host}") or host
    return guess_company_name(domain.split(".")[0])


# Elements that carry no posting and only spend the model's small context.
_DROP_TAGS = (
    "script", "style", "noscript", "svg", "iframe", "head", "link", "meta", "img", "picture",
    "video", "form", "input", "button", "select", "textarea",
)  # fmt: skip
_KEEP_ATTRS = ("class", "id", "href")
_TEXT_LIMIT = 80
_HREF_LIMIT = 120
# Repeated sibling blocks (a list of postings) are shown a few times, not hundreds.
_REPEATS = 3


def compact_html(html: str, *, limit: int = 12_000) -> str:
    """Return a small outline of a page for the model: structure, classes, links, short texts.

    Scripts, styles and forms are removed, only ``class``, ``id`` and ``href`` attributes are kept,
    texts are shortened, and runs of identical sibling blocks are cut to a few, so the selectors the
    model needs (the repeated posting block and what is inside it) fit a small context.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(_DROP_TAGS):
        tag.decompose()
    root = soup.body or soup
    for tag in root.find_all(True):
        if not isinstance(tag, Tag):
            continue
        kept: dict[str, Any] = {k: v for k, v in tag.attrs.items() if k in _KEEP_ATTRS}
        if isinstance(kept.get("href"), str):
            kept["href"] = kept["href"][:_HREF_LIMIT]
        tag.attrs = kept
    for text in root.find_all(string=True):
        shortened = " ".join(str(text).split())[:_TEXT_LIMIT]
        text.replace_with(shortened)
    for parent in [root, *root.find_all(True)]:
        if not isinstance(parent, Tag):
            continue
        run: list[Tag] = []
        signature: tuple[str, tuple[str, ...]] | None = None
        for child in list(parent.children):
            if not isinstance(child, Tag):
                continue
            current = (child.name, tuple(child.get("class") or ()))
            if current == signature:
                run.append(child)
                if len(run) > _REPEATS:
                    child.decompose()
            else:
                signature, run = current, [child]
    outline = " ".join(str(root).split())
    return outline[:limit]
