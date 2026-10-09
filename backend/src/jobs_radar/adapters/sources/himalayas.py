"""Himalayas job board adapter (ADR-049, research R-00173).

Free public API, no key. The browse feed has over 100,000 postings, so the adapter uses the search
endpoint, newest first: one stream per country of the owner (``country=XX`` without worldwide
jobs) and one for worldwide remote work. Himalayas states, per job, the countries where the work
may be done, which makes its country filter exact. Data refreshes every 24 hours.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from jobs_radar.adapters.sources.base import SourceError, SourcePosting
from jobs_radar.adapters.sources.catalogue import require_entry
from jobs_radar.adapters.sources.countries import country_code
from jobs_radar.adapters.sources.html_text import html_to_text
from jobs_radar.adapters.sources.job_board import (
    MAX_PAGES_PER_STREAM,
    Candidate,
    JobBoardAdapter,
    MalformedPostingError,
    Page,
    Stream,
)
from jobs_radar.domain.enums import SourceErrorClass
from jobs_radar.domain.job_board_rules import UNKNOWN, WORLDWIDE, Eligibility, Reach
from jobs_radar.schemas.source_filters import JobBoardFilters

_ENTRY = require_entry("himalayas")
_PAGE_SIZE = 20


def _text(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _restriction(entry: object) -> tuple[str, str | None]:
    """Return ``(name, iso_code)`` of a location restriction given as a string or an object."""
    if isinstance(entry, str):
        return entry.strip(), country_code(entry)
    if isinstance(entry, dict):
        name = _text(entry.get("name"))
        alpha2 = entry.get("alpha2")
        code = (
            alpha2.upper() if isinstance(alpha2, str) and len(alpha2) == 2 else country_code(name)
        )
        return name or (code or ""), code
    return "", None


def _salary_line(job: dict[str, Any]) -> str:
    low, high = job.get("minSalary"), job.get("maxSalary")
    if not isinstance(low, int | float) and not isinstance(high, int | float):
        return ""
    amount = "-".join(f"{value:g}" for value in (low, high) if isinstance(value, int | float))
    unit = " ".join(_text(job.get(key)) for key in ("currency", "salaryPeriod")).strip()
    return f"Salary stated by the board: {amount} {unit}".strip()


def parse_job(job: object) -> Candidate:
    """Convert one Himalayas job object into a candidate; raises :class:`MalformedPostingError`."""
    if not isinstance(job, dict):
        raise MalformedPostingError
    guid, title = job.get("guid"), _text(job.get("title"))
    company = _text(job.get("companyName"))
    apply_link = job.get("applicationLink")
    if not isinstance(guid, str) or not guid or not title or not company:
        raise MalformedPostingError
    restrictions = [_restriction(entry) for entry in job.get("locationRestrictions") or []]
    restrictions = [(name, code) for name, code in restrictions if name or code]
    codes = frozenset(code for _, code in restrictions if code)
    if not restrictions:
        eligibility = WORLDWIDE
    elif codes:
        eligibility = Eligibility(Reach.COUNTRIES, codes)
    else:
        eligibility = UNKNOWN
    published = job.get("pubDate")
    posted_at = (
        datetime.fromtimestamp(published, UTC)
        if isinstance(published, int | float) and not isinstance(published, bool)
        else None
    )
    text = html_to_text(job["description"] if isinstance(job.get("description"), str) else None)
    salary = _salary_line(job)
    parents = _strings(job.get("parentCategories"))
    posting = SourcePosting(
        external_job_id=guid,
        title=title,
        source_url=guid,
        apply_url=apply_link if isinstance(apply_link, str) and apply_link else guid,
        description_text=f"{text}\n\n{salary}".strip() if salary else text,
        locations=tuple(name for name, _ in restrictions) or ("Worldwide",),
        posted_at=posted_at,
        source_updated_at=None,
        departments=parents,
        language=None,
        raw_payload=job,
        company_name=company,
    )
    return Candidate(posting, eligibility, (*parents, *_strings(job.get("categories"))))


class HimalayasAdapter(JobBoardAdapter):
    """Collects the Himalayas remote job board."""

    entry = _ENTRY
    source_type = _ENTRY.source_type

    def _streams(
        self, filters: JobBoardFilters, *, per_minute: int, credential: str | None
    ) -> list[Stream]:
        def stream(selector: dict[str, str]) -> Stream:
            async def pages() -> AsyncIterator[Page]:
                for number in range(1, MAX_PAGES_PER_STREAM + 1):
                    query = {**selector, "sort": "recent", "limit": _PAGE_SIZE, "page": number}
                    listing: Any = await self._get_json(
                        f"{self.entry.endpoint}/search?{urlencode(query)}", per_minute=per_minute
                    )
                    if not isinstance(listing, dict) or not isinstance(listing.get("jobs"), list):
                        msg = "The answer does not contain a list of jobs."
                        raise SourceError(SourceErrorClass.INVALID_PAYLOAD, msg)
                    candidates: list[Candidate] = []
                    skipped = 0
                    for job in listing["jobs"]:
                        try:
                            candidates.append(parse_job(job))
                        except MalformedPostingError:
                            skipped += 1
                    total, offset = listing.get("totalCount"), listing.get("offset")
                    total = total if isinstance(total, int) else None
                    offset = offset if isinstance(offset, int) else (number - 1) * _PAGE_SIZE
                    has_more = (
                        bool(listing["jobs"])
                        and total is not None
                        and offset + len(listing["jobs"]) < total
                    )
                    # The total is counted once per stream, on its first page.
                    yield Page(
                        candidates,
                        skipped=skipped,
                        has_more=has_more,
                        declared_total=total if number == 1 else None,
                    )
                    if not has_more:
                        return

            return pages

        streams = [
            stream({"country": code, "exclude_worldwide": "true"}) for code in filters.country_codes
        ]
        if filters.include_worldwide:
            streams.append(stream({"worldwide": "true"}))
        return streams
