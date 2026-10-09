"""Jobicy job board adapter (ADR-049, research R-00173).

Free public API, no key: ``/api/v2/remote-jobs`` with ``geo`` and cursor paging. Jobicy asks for
at most one automated poll an hour and for the original job link to be kept. One stream is read
per geographic slug the owner's countries need: ``europe`` for European countries, ``anywhere``
for worldwide remote work, a country slug otherwise.
"""

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from jobs_radar.adapters.sources.base import SourceError, SourcePosting
from jobs_radar.adapters.sources.catalogue import require_entry
from jobs_radar.adapters.sources.countries import country_code, country_name
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
from jobs_radar.domain.job_board_rules import LocationScope, eligibility_from_regions
from jobs_radar.domain.regions import EUROPE
from jobs_radar.schemas.source_filters import JobBoardFilters

_ENTRY = require_entry("jobicy")
_PAGE_SIZE = 100
# Jobicy's slug for the United States is not the country name.
_SLUG_EXCEPTIONS = {"US": "usa"}


def _text(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def geo_slugs(scope: LocationScope) -> list[str]:
    """Return the Jobicy ``geo`` slugs covering the owner's countries (and worldwide, if wanted)."""
    slugs: list[str] = []
    codes = sorted(scope.country_codes)
    # Remote work from anywhere also reaches European postings, so both big regions are read.
    if scope.any_country or any(code in EUROPE for code in codes):
        slugs.append("europe")
    for code in codes:
        if code in EUROPE:
            continue
        name = country_name(code)
        slug = _SLUG_EXCEPTIONS.get(code) or (re.sub(r"\W+", "-", name.lower()) if name else "")
        if slug and slug not in slugs:
            slugs.append(slug)
    if scope.include_worldwide or scope.any_country:
        slugs.append("anywhere")
    return slugs


def _salary_line(job: dict[str, Any]) -> str:
    low, high = job.get("salaryMin"), job.get("salaryMax")
    if not isinstance(low, int | float) and not isinstance(high, int | float):
        return ""
    amount = "-".join(f"{value:g}" for value in (low, high) if isinstance(value, int | float))
    unit = " ".join(_text(job.get(key)) for key in ("salaryCurrency", "salaryPeriod")).strip()
    return f"Salary stated by the board: {amount} {unit}".strip()


def parse_job(job: object) -> Candidate:
    """Convert one Jobicy job object into a candidate; raises :class:`MalformedPostingError`."""
    if not isinstance(job, dict):
        raise MalformedPostingError
    raw_id, title, url = job.get("id"), _text(job.get("jobTitle")), job.get("url")
    company = _text(job.get("companyName"))
    if raw_id in (None, "") or not title or not company or not isinstance(url, str) or not url:
        raise MalformedPostingError
    published = job.get("pubDate")
    try:
        posted_at = datetime.fromisoformat(published) if isinstance(published, str) else None
    except ValueError:
        posted_at = None
    if posted_at is not None and posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)
    geo = tuple(part.strip() for item in _strings(job.get("jobGeo")) for part in item.split(","))
    regions = [code or name for name in geo if name for code in [country_code(name)]]
    body = job.get("jobDescription") or job.get("jobExcerpt")
    text = html_to_text(body if isinstance(body, str) else None)
    salary = _salary_line(job)
    industries = _strings(job.get("jobIndustry"))
    posting = SourcePosting(
        external_job_id=str(raw_id),
        title=title,
        source_url=url,
        apply_url=url,
        description_text=f"{text}\n\n{salary}".strip() if salary else text,
        locations=geo,
        posted_at=posted_at,
        source_updated_at=None,
        departments=industries,
        language=None,
        raw_payload=job,
        company_name=company,
    )
    return Candidate(
        posting, eligibility_from_regions(regions), (*industries, *_strings(job.get("jobType")))
    )


class JobicyAdapter(JobBoardAdapter):
    """Collects the Jobicy remote job board."""

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
        def stream(slug: str) -> Stream:
            async def pages() -> AsyncIterator[Page]:
                cursor: str | None = None
                for _ in range(MAX_PAGES_PER_STREAM):
                    query: dict[str, str | int] = {"count": _PAGE_SIZE, "geo": slug}
                    if cursor:
                        query["cursor"] = cursor
                    listing: Any = await self._get_json(
                        f"{self.entry.endpoint}?{urlencode(query)}", per_minute=per_minute
                    )
                    if (
                        not isinstance(listing, dict)
                        or listing.get("success") is False
                        or not isinstance(listing.get("jobs"), list)
                    ):
                        msg = "The answer does not contain a list of jobs."
                        raise SourceError(SourceErrorClass.INVALID_PAYLOAD, msg)
                    candidates: list[Candidate] = []
                    skipped = 0
                    for job in listing["jobs"]:
                        try:
                            candidates.append(parse_job(job))
                        except MalformedPostingError:
                            skipped += 1
                    cursor = (
                        listing.get("nextCursor")
                        if isinstance(listing.get("nextCursor"), str)
                        else None
                    )
                    has_more = listing.get("hasMore") is True and cursor is not None
                    yield Page(candidates, skipped=skipped, has_more=has_more)
                    if not has_more:
                        return

            return pages

        return [stream(slug) for slug in geo_slugs(scope)]
