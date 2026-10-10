"""Reads a few public pages of a company's own website (ADR-054).

Only pages of the website's registered domain are read (a redirect to another domain drops the
page), ``robots.txt`` is honoured per host, requests are spaced out, and the number of pages, their
size and the time are bounded. Every request goes through the one guarded HTTP client. The result
is plain text per page; nothing is stored here and nothing leaves the machine.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from jobs_radar.core.http import FetchError, GuardedHttpClient
from jobs_radar.domain.domains import registered_domain

# Pages worth reading to understand a company, matched on the link's address or its text.
_KEYWORDS = (
    "about", "company", "who-we-are", "careers", "jobs", "engineering", "tech", "blog",
    "remote", "culture", "values", "handbook", "how-we-work", "team", "life", "benefits",
)  # fmt: skip
# The characters kept from one page: enough for the model, small enough for a local context window.
PAGE_TEXT_LIMIT = 6000
_MAX_PAGE_BYTES = 1_500_000
# Page furniture that says nothing about the company; dropped before the text is cut to size.
_NOISE_TAGS = (
    "script", "style", "noscript", "template", "svg", "iframe", "nav", "header", "footer",
    "aside", "form", "button", "select",
)  # fmt: skip
# A line shorter than this is a menu entry or a label, not a sentence.
_MIN_WORDS = 3


@dataclass(frozen=True)
class WebPage:
    """One page of the company website, reduced to text."""

    url: str
    text: str


def page_text(html: str) -> str:
    """Return the readable text of a page: main content only, one line per block, no menus.

    Navigation, headers, footers, forms and scripts are removed, ``<main>`` is preferred when the
    page has one, and lines of fewer than three words (menu entries, labels) are dropped.
    """
    if not html.strip():
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(_NOISE_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.body or soup
    lines: list[str] = []
    for raw in root.get_text("\n").splitlines():
        line = " ".join(raw.split())
        if len(line.split()) >= _MIN_WORDS and (not lines or lines[-1] != line):
            lines.append(line)
    return "\n".join(lines)


def select_page_links(home_url: str, html: str, *, limit: int) -> list[str]:
    """Pick up to ``limit`` same-domain links that look like about, careers or culture pages."""
    domain = registered_domain(home_url)
    soup = BeautifulSoup(html, "lxml")
    scored: dict[str, int] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        url, _ = urldefrag(urljoin(home_url, href))
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or registered_domain(url) != domain:
            continue
        haystack = f"{parts.path} {anchor.get_text(' ', strip=True)}".lower()
        score = sum(1 for word in _KEYWORDS if word in haystack)
        if score and url.rstrip("/") != home_url.rstrip("/"):
            scored.setdefault(url, score)
    # Highest score first; the dict keeps document order for ties.
    ranked = sorted(scored, key=lambda url: -scored[url])
    return ranked[:limit]


class WebsiteReader:
    """Fetches the home page and a few relevant pages of one website."""

    def __init__(
        self,
        client: GuardedHttpClient,
        *,
        max_pages: int = 8,
        min_interval: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._max_pages = max_pages
        self._min_interval = min_interval
        self._sleep = sleep
        self._robots: dict[str, RobotFileParser | None] = {}

    async def _allowed(self, url: str) -> bool:
        """Whether ``robots.txt`` of the page's host allows it (unreadable robots allow it)."""
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser: RobotFileParser | None = None
            try:
                response = await self._client.get(f"{origin}/robots.txt")
                if response.status == 200:
                    parser = RobotFileParser()
                    parser.parse(response.body.decode("utf-8", "replace").splitlines())
            except FetchError:
                parser = None
            self._robots[origin] = parser
        parser = self._robots[origin]
        return parser is None or parser.can_fetch("*", url)

    async def _page(self, url: str, domain: str | None) -> tuple[str, str] | None:
        """Return ``(final_url, html)`` of a readable HTML page on ``domain``, else ``None``."""
        if not await self._allowed(url):
            return None
        await self._sleep(self._min_interval)
        try:
            response = await self._client.get(url)
        except FetchError:
            return None
        content_type = response.headers.get("content-type", "text/html")
        if (
            response.status != 200
            or registered_domain(response.url) != domain
            or "html" not in content_type
            or len(response.body) > _MAX_PAGE_BYTES
        ):
            return None
        return response.url, response.body.decode("utf-8", "replace")

    async def read(self, home_url: str) -> list[WebPage]:
        """Read the home page and the pages it links to; an unreadable home gives ``[]``."""
        domain = registered_domain(home_url)
        home = await self._page(home_url, domain)
        if home is None:
            return []
        pages = [WebPage(home_url, page_text(home[1])[:PAGE_TEXT_LIMIT])]
        links = select_page_links(home_url, home[1], limit=self._max_pages - 1)
        for link in links:
            page = await self._page(link, domain)
            if page is not None:
                pages.append(WebPage(link, page_text(page[1])[:PAGE_TEXT_LIMIT]))
        return [p for p in pages if p.text]
