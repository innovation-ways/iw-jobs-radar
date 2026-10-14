"""A company's own careers site, read through schema.org ``JobPosting`` structured data (ADR-070).

Many employers publish every posting page with a ``JobPosting`` in JSON-LD because Google for Jobs
requires it. This adapter needs no knowledge of the site's layout and uses no AI: the posting pages
are found in the sitemap (``robots.txt`` ``Sitemap:`` lines, then ``/sitemap.xml``; an index is
followed to its job-like sitemaps) or, failing that, in the links of the careers page; each page is
read once and its ``JobPosting`` is mapped. Only pages of the company's own registered domain are
read, ``robots.txt`` is honoured (a refusal stops the source, it is never worked around), requests
are spaced by the source's rate limit, and a run reads at most ``MAX_PAGES_PER_RUN`` posting pages,
newest first, so a larger site is ``partial`` and never closes postings.

The sitemap content is hashed into the checkpoint ETag: when the list of pages and their
``lastmod`` dates are unchanged, no posting page is read.
"""

import asyncio
import hashlib
import html as html_lib
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit

from bs4 import BeautifulSoup

from jobs_radar.adapters.sources.base import (
    BoardInfo,
    CollectionResult,
    RateLimiter,
    SourceCheckpoint,
    SourceError,
    SourcePosting,
)
from jobs_radar.adapters.sources.company_board import (
    clean,
    distinct,
    from_iso,
    guess_company_name,
)
from jobs_radar.adapters.sources.html_text import html_to_text
from jobs_radar.adapters.sources.polite_http import PoliteGetter
from jobs_radar.adapters.sources.robots import RobotsGate
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.domain.careers_markers import page_address
from jobs_radar.domain.domains import registered_domain
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters

MAX_PAGES_PER_RUN = 200
_MAX_SITEMAPS = 6
_MAX_PAGE_BYTES = 3_000_000
_SAMPLE = 3
# A sitemap whose own address says it lists jobs; every entry of it is a posting page.
_JOB_SITEMAP = re.compile(r"job|vacanc|career|position|posting|opening", re.IGNORECASE)
# A page address that looks like one posting: a job-like path word followed by one more segment.
_POSTING_PATH = re.compile(
    r"(?:^|/)(?:jobs?|vacanc(?:y|ies)|positions?|openings?|postings?|requisitions?|careers?"
    r"|opportunit(?:y|ies))/[^/]+",
    re.IGNORECASE,
)
_BLOCK = re.compile(r"<(url|sitemap)>(.*?)</\1>", re.S | re.IGNORECASE)
_LOC = re.compile(r"<loc>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</loc>", re.S | re.IGNORECASE)
_LASTMOD = re.compile(r"<lastmod>\s*(.*?)\s*</lastmod>", re.S | re.IGNORECASE)
_HEADERS = {"Accept": "text/html,application/xml;q=0.9,*/*;q=0.5"}


def _node_list(value: Any) -> list[Any]:
    """Return ``value`` as a list (JSON-LD lets a single object stand for a list of one)."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _find_job_posting(node: Any) -> dict[str, Any] | None:
    """Return the first ``JobPosting`` object in a JSON-LD value (lists and ``@graph`` included)."""
    for item in _node_list(node):
        if not isinstance(item, dict):
            continue
        types = _node_list(item.get("@type"))
        if "JobPosting" in types:
            return item
        found = _find_job_posting(item.get("@graph"))
        if found is not None:
            return found
    return None


def _country_name(value: Any) -> str:
    """Name of a country given as text or as a ``Country`` object."""
    if isinstance(value, dict):
        return clean(value.get("name"))
    return clean(value)


def _places(posting: dict[str, Any]) -> list[str]:
    """Locations of a posting; remote work becomes ``Remote`` or ``Remote - <country>``."""
    places: list[str] = []
    for place in _node_list(posting.get("jobLocation")):
        address = place.get("address") if isinstance(place, dict) else place
        if isinstance(address, dict):
            parts = [
                clean(address.get("addressLocality")),
                clean(address.get("addressRegion")),
                _country_name(address.get("addressCountry")),
            ]
            places.append(", ".join(part for part in parts if part))
        elif isinstance(address, str):
            places.append(clean(address))
    remote = posting.get("jobLocationType") == "TELECOMMUTE"
    requirements = [
        _country_name(item) or _country_name(item.get("name") if isinstance(item, dict) else None)
        for item in _node_list(posting.get("applicantLocationRequirements"))
    ]
    names = [name for name in requirements if name]
    if remote:
        places.extend(f"Remote - {name}" for name in names)
        if not names:
            places.append("Remote")
    return list(distinct(places))


def parse_job_posting(page_html: str, url: str, now: datetime) -> SourcePosting | None:
    """Map the ``JobPosting`` of a posting page, or ``None`` when it has none or has expired."""
    soup = BeautifulSoup(page_html, "lxml")
    posting: dict[str, Any] | None = None
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except ValueError:
            continue
        posting = _find_job_posting(data)
        if posting is not None:
            break
    if posting is None:
        return None
    title = clean(posting.get("title"))
    description = posting.get("description")
    if not title or not isinstance(description, str):
        return None
    valid_through = from_iso(posting.get("validThrough"))
    if valid_through is not None and valid_through < now:
        return None
    canonical, _ = urldefrag(url)
    listed = posting.get("url")
    return SourcePosting(
        external_job_id=canonical,
        title=title,
        source_url=canonical,
        apply_url=listed if isinstance(listed, str) and listed.startswith("http") else canonical,
        description_text=html_to_text(description),
        locations=tuple(_places(posting)),
        posted_at=from_iso(posting.get("datePosted")),
        source_updated_at=None,
        departments=distinct([clean(posting.get("occupationalCategory"))]),
        language=None,
        raw_payload=posting,
    )


def _entries(xml: str, tag: str) -> list[tuple[str, str | None]]:
    """``(address, lastmod)`` of each ``<url>`` or ``<sitemap>`` block of a sitemap document."""
    found: list[tuple[str, str | None]] = []
    for kind, body in _BLOCK.findall(xml):
        if kind.lower() != tag:
            continue
        loc = _LOC.search(body)
        if loc is None:
            continue
        modified = _LASTMOD.search(body)
        found.append(
            (html_lib.unescape(loc.group(1).strip()), modified.group(1) if modified else None)
        )
    return found


class PageJsonLdAdapter:
    """Collects the structured postings of a company's own careers site."""

    source_type = SourceType.PAGE_JSONLD

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
            not_found_message="The careers page or its sitemap was not found.",
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    def endpoint(self, identifier: str) -> str:
        """Return the careers address stored in the source configuration."""
        return page_address(identifier)

    # --- finding the posting pages -------------------------------------------------------------

    async def _text(self, url: str, key: str, per_minute: int) -> str:
        response = await self._getter.get(url, _HEADERS, key, per_minute=per_minute)
        if len(response.body) > _MAX_PAGE_BYTES:
            raise SourceError(SourceErrorClass.TOO_LARGE, "A page of the site is too large.")
        return response.body.decode("utf-8", "replace")

    async def _sitemap_pages(
        self, address: str, gate: RobotsGate, key: str, per_minute: int
    ) -> list[tuple[str, str | None]]:
        """Return the posting pages the site's sitemaps name (``[]`` when none are listed)."""
        origin = f"{urlsplit(address).scheme}://{urlsplit(address).netloc}"
        queue = await gate.sitemaps(address) or [f"{origin}/sitemap.xml"]
        domain = registered_domain(address)
        pages: dict[str, str | None] = {}
        fetched = 0
        while queue and fetched < _MAX_SITEMAPS:
            sitemap = queue.pop(0)
            if sitemap.endswith(".gz") or registered_domain(sitemap) != domain:
                continue
            fetched += 1
            try:
                xml = await self._text(sitemap, key, per_minute)
            except SourceError as error:
                if error.error_class in (SourceErrorClass.NOT_FOUND, SourceErrorClass.HTTP_ERROR):
                    continue
                raise
            children = [loc for loc, _ in _entries(xml, "sitemap")]
            if children:
                # Only the path says what a sitemap lists: the host may contain "careers".
                job_like = [c for c in children if _JOB_SITEMAP.search(urlsplit(c).path)]
                queue = (job_like or children[:2]) + queue
                continue
            job_sitemap = _JOB_SITEMAP.search(urlsplit(sitemap).path) is not None
            for loc, modified in _entries(xml, "url"):
                same_site = registered_domain(loc) == domain
                if same_site and (job_sitemap or _POSTING_PATH.search(urlsplit(loc).path)):
                    pages.setdefault(urldefrag(loc)[0], modified)
        return list(pages.items())

    async def _linked_pages(
        self, address: str, key: str, per_minute: int
    ) -> list[tuple[str, str | None]]:
        """Posting-like links of the careers page itself, on the company's own domain."""
        soup = BeautifulSoup(await self._text(address, key, per_minute), "lxml")
        domain = registered_domain(address)
        pages: dict[str, str | None] = {}
        for anchor in soup.find_all("a", href=True):
            url = urldefrag(urljoin(address, str(anchor["href"]).strip()))[0]
            parts = urlsplit(url)
            if (
                parts.scheme in {"http", "https"}
                and registered_domain(url) == domain
                and _POSTING_PATH.search(parts.path)
            ):
                pages.setdefault(url, None)
        return list(pages.items())

    async def _posting_pages(
        self, identifier: str, key: str, per_minute: int
    ) -> list[tuple[str, str | None]]:
        """Every posting page of the site, newest first (pages with no date last)."""
        address = self.endpoint(identifier)
        gate = RobotsGate(self._client)
        if not await gate.allowed(address):
            msg = "The site's robots.txt does not allow automated reading of its careers pages."
            raise SourceError(SourceErrorClass.CONFIGURATION, msg)
        pages = await self._sitemap_pages(address, gate, key, per_minute)
        if not pages:
            pages = await self._linked_pages(address, key, per_minute)
        # ISO dates sort as text; an absent date sorts last.
        return sorted(pages, key=lambda item: item[1] or "", reverse=True)

    # --- reading a posting page ----------------------------------------------------------------

    async def _posting(
        self, url: str, key: str, per_minute: int, gate: RobotsGate
    ) -> SourcePosting | None:
        if not await gate.allowed(url):
            return None
        return parse_job_posting(await self._text(url, key, per_minute), url, self._clock())

    # --- the adapter contract ------------------------------------------------------------------

    async def validate(
        self,
        identifier: str,
        credential: str | None = None,
        filters: JobBoardFilters | None = None,
        scope: LocationScope | None = None,
    ) -> BoardInfo:
        """Check that the site publishes structured postings, reading at most three pages."""
        pages = await self._posting_pages(identifier, identifier, 6)
        gate = RobotsGate(self._client)
        for url, _ in pages[:_SAMPLE]:
            try:
                posting = await self._posting(url, identifier, 6, gate)
            except SourceError:
                continue
            if posting is not None:
                domain = registered_domain(self.endpoint(identifier)) or identifier
                return BoardInfo(
                    name=guess_company_name(domain.split(".")[0]), postings_count=len(pages)
                )
        msg = "No structured postings (schema.org JobPosting) were found on this careers site."
        raise SourceError(SourceErrorClass.NOT_FOUND, msg, http_status=200)

    async def collect(self, checkpoint: SourceCheckpoint) -> CollectionResult:
        """Read the newest posting pages, or report that the sitemap did not change."""
        started = asyncio.get_running_loop().time()
        key, per_minute = checkpoint.identifier, checkpoint.rate_limit_per_minute
        pages = await self._posting_pages(checkpoint.identifier, key, per_minute)
        digest = hashlib.sha256(
            "\n".join(f"{url}|{modified or ''}" for url, modified in pages).encode()
        ).hexdigest()
        if pages and checkpoint.etag == digest:
            duration = int((asyncio.get_running_loop().time() - started) * 1000)
            return CollectionResult("not_modified", (), digest, 304, duration, None)
        gate = RobotsGate(self._client)
        postings: list[SourcePosting] = []
        dropped = 0
        incomplete = len(pages) > MAX_PAGES_PER_RUN
        for url, _ in pages[:MAX_PAGES_PER_RUN]:
            try:
                posting = await self._posting(url, key, per_minute, gate)
            except SourceError as error:
                if error.error_class is SourceErrorClass.NOT_FOUND or error.http_status == 410:
                    dropped += 1  # the page is gone: simply not an open posting any more
                else:
                    incomplete = True  # could not be read: nothing may be closed on this run
                continue
            if posting is None:
                dropped += 1
            else:
                postings.append(posting)
        duration = int((asyncio.get_running_loop().time() - started) * 1000)
        return CollectionResult(
            "modified",
            tuple(postings),
            None if incomplete else digest,
            200,
            duration,
            len(pages),
            dropped_count=dropped,
            truncated=incomplete,
        )
