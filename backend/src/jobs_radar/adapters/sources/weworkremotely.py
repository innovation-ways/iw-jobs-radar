"""We Work Remotely job board adapter (ADR-072, research R-00173).

The board publishes public RSS feeds, no key: one with the newest postings of every category and
one per category. Each feed holds only the newest few dozen postings, so the adapter reads them
all (one request each) and removes repeats. A posting names its company in the title
(``Company: Role``), its remote region in ``region`` and, when the work is restricted, the
eligible countries in ``country`` (written with flags). No posting date other than ``pubDate`` and
no salary field is published.
"""

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from bs4 import BeautifulSoup, Tag

from jobs_radar.adapters.sources.base import SourceError, SourcePosting
from jobs_radar.adapters.sources.catalogue import require_entry
from jobs_radar.adapters.sources.countries import country_code
from jobs_radar.adapters.sources.html_text import html_to_text
from jobs_radar.adapters.sources.job_board import (
    Candidate,
    JobBoardAdapter,
    MalformedPostingError,
    Page,
    Stream,
)
from jobs_radar.domain.enums import SourceErrorClass
from jobs_radar.domain.job_board_rules import (
    UNKNOWN,
    WORLDWIDE,
    Eligibility,
    LocationScope,
    Reach,
    eligibility_from_regions,
)
from jobs_radar.schemas.source_filters import JobBoardFilters

_ENTRY = require_entry("weworkremotely")
_ORIGIN = "https://weworkremotely.com/"
# The newest postings of everything, then each category feed (the "all other" and "data science"
# categories have no feed of their own: they redirect).
FEEDS: tuple[str, ...] = (
    "remote-jobs.rss",
    "categories/remote-full-stack-programming-jobs.rss",
    "categories/remote-back-end-programming-jobs.rss",
    "categories/remote-front-end-programming-jobs.rss",
    "categories/remote-devops-sysadmin-jobs.rss",
    "categories/remote-product-jobs.rss",
    "categories/remote-design-jobs.rss",
    "categories/remote-customer-support-jobs.rss",
    "categories/remote-sales-and-marketing-jobs.rss",
    "categories/remote-management-and-finance-jobs.rss",
)
_WORLD_REGION = "anywhere in the world"
# The board writes "Remote - Americas" and "USA Only"; only the place itself is wanted.
_REGION_AFFIX = re.compile(r"^\s*remote\s*[-\N{EN DASH}\N{EM DASH}:]\s*|\s+only\s*$", re.IGNORECASE)
_LEADING_JUNK = re.compile(r"^[^A-Za-z]+")
_LEADING_AND = re.compile(r"^and\s+", re.IGNORECASE)
_HEADQUARTERS = re.compile(r"Headquarters:\s*(.+)")
# Country names the offline GeoNames list writes differently from this board.
_NAME_PREFIXES = {"united kingdom": "GB", "united states": "US"}


def _field(item: Tag, name: str) -> str:
    found = item.find(name)
    return " ".join(found.get_text().split()) if isinstance(found, Tag) else ""


def _country_names(text: str) -> list[str]:
    """Split ``🇵🇹 Portugal, 🇪🇸 Spain, and 🇩🇪 Germany`` into plain country names."""
    names: list[str] = []
    for part in text.split(","):
        # The last name follows "and", and every name follows its flag.
        name = _LEADING_JUNK.sub("", _LEADING_AND.sub("", _LEADING_JUNK.sub("", part.strip())))
        if name.strip():
            names.append(name.strip())
    return names


def _code(name: str) -> str | None:
    lowered = name.lower()
    for prefix, code in _NAME_PREFIXES.items():
        if lowered.startswith(prefix):
            return code
    return country_code(name)


def _eligibility(region: str, countries_text: str) -> tuple[Eligibility, tuple[str, ...]]:
    """Return the eligibility of a posting and the place names to show for it."""
    names = _country_names(countries_text)
    if names:
        codes = [_code(name) for name in names]
        # One unreadable name makes the whole list unreliable: keep the posting for the judgement.
        if all(codes):
            return Eligibility(Reach.COUNTRIES, frozenset(code for code in codes if code)), tuple(
                names
            )
        return UNKNOWN, tuple(names)
    cleaned = _REGION_AFFIX.sub("", region).strip()
    if not cleaned or cleaned.lower() == _WORLD_REGION:
        return WORLDWIDE, ("Worldwide",)
    return eligibility_from_regions([_code(cleaned) or cleaned]), (cleaned,)


def _split_title(title: str, description: str) -> tuple[str, str]:
    """Return ``(company, role)``: from ``Company: Role``, else the description's headquarters."""
    company, separator, role = title.partition(": ")
    if separator and company.strip() and role.strip():
        return company.strip(), role.strip()
    found = _HEADQUARTERS.search(description)
    return (found.group(1).strip(), title) if found else ("", title)


def parse_item(item: Tag) -> Candidate:
    """Convert one RSS ``item`` into a candidate; raises :class:`MalformedPostingError`."""
    guid, link = _field(item, "guid"), _field(item, "link")
    raw_title = _field(item, "title")
    description_tag = item.find("description")
    html = description_tag.get_text() if isinstance(description_tag, Tag) else ""
    text = html_to_text(html)
    company, title = _split_title(raw_title, text)
    if not guid or not link or not title or not company:
        raise MalformedPostingError
    try:
        posted_at: datetime | None = parsedate_to_datetime(_field(item, "pubDate"))
    except (TypeError, ValueError):
        posted_at = None
    if posted_at is not None and posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)
    eligibility, places = _eligibility(_field(item, "region"), _field(item, "country"))
    category = _field(item, "category")
    posting = SourcePosting(
        external_job_id=guid,
        title=title,
        source_url=link,
        apply_url=link,
        description_text=text,
        locations=places,
        posted_at=posted_at,
        source_updated_at=None,
        departments=(category,) if category else (),
        language=None,
        raw_payload={
            "title": raw_title,
            "region": _field(item, "region"),
            "country": _field(item, "country"),
            "category": category,
            "skills": _field(item, "skills"),
            "type": _field(item, "type"),
            "link": link,
        },
        company_name=company,
    )
    areas = tuple(
        value for value in (category, _field(item, "skills"), _field(item, "type")) if value
    )
    return Candidate(posting, eligibility, areas)


class WeWorkRemotelyAdapter(JobBoardAdapter):
    """Collects the We Work Remotely RSS feeds."""

    entry = _ENTRY
    source_type = _ENTRY.source_type

    def _streams(
        self,
        filters: JobBoardFilters,
        scope: LocationScope,
        *,
        per_minute: int,
        credential: str | None,
    ) -> list[Stream]:
        def stream(path: str) -> Stream:
            async def pages() -> AsyncIterator[Page]:
                response = await self._getter.get(
                    _ORIGIN + path, {}, self.entry.catalogue_key, per_minute=per_minute
                )
                # The "xml" parser reads the feed without resolving entities or fetching anything.
                soup = BeautifulSoup(response.body, "xml")
                channel: Any = soup.find("channel")
                if not isinstance(channel, Tag):
                    msg = "The answer is not an RSS feed."
                    raise SourceError(SourceErrorClass.INVALID_PAYLOAD, msg)
                candidates: list[Candidate] = []
                skipped = 0
                for item in channel.find_all("item"):
                    try:
                        candidates.append(parse_item(item))
                    except MalformedPostingError:
                        skipped += 1
                yield Page(candidates, skipped=skipped)

            return pages

        return [stream(path) for path in FEEDS]
