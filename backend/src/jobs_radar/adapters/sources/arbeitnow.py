"""Arbeitnow job board adapter (ADR-049, research R-00173).

Free public API, no key: ``/api/job-board-api?page=N``, newest first, updated hourly. The board
aggregates postings from several ATS, so the same job can also be on a company board; the pipeline
links those (ADR-023). Arbeitnow states no eligibility, only a ``remote`` flag and a place, so the
country is read from the place text and an unreadable place is kept for the later judgement.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from jobs_radar.adapters.sources.base import SourceError, SourcePosting
from jobs_radar.adapters.sources.catalogue import require_entry
from jobs_radar.adapters.sources.countries import country_of_place
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
from jobs_radar.domain.job_board_rules import UNKNOWN, Eligibility, LocationScope, Reach
from jobs_radar.schemas.source_filters import JobBoardFilters

_ENTRY = require_entry("arbeitnow")


def _text(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def parse_job(job: object) -> Candidate:
    """Convert one Arbeitnow job object into a candidate; raises :class:`MalformedPostingError`."""
    if not isinstance(job, dict):
        raise MalformedPostingError
    slug, title, url = _text(job.get("slug")), _text(job.get("title")), job.get("url")
    company = _text(job.get("company_name"))
    if not slug or not title or not company or not isinstance(url, str) or not url:
        raise MalformedPostingError
    location = _text(job.get("location"))
    remote = job.get("remote") is True
    created = job.get("created_at")
    posted_at = (
        datetime.fromtimestamp(created, UTC)
        if isinstance(created, int | float) and not isinstance(created, bool)
        else None
    )
    code = country_of_place(location) if location else None
    eligibility = Eligibility(Reach.COUNTRIES, frozenset({code})) if code else UNKNOWN
    tags = _strings(job.get("tags"))
    job_types = _strings(job.get("job_types"))
    locations = tuple(item for item in (location, "Remote" if remote else "") if item)
    description = job.get("description")
    posting = SourcePosting(
        external_job_id=slug,
        title=title,
        source_url=url,
        apply_url=url,
        description_text=html_to_text(description if isinstance(description, str) else None),
        locations=locations,
        posted_at=posted_at,
        source_updated_at=None,
        departments=tags,
        language=None,
        raw_payload=job,
        company_name=company,
    )
    return Candidate(posting, eligibility, (*tags, *job_types))


class ArbeitnowAdapter(JobBoardAdapter):
    """Collects the Arbeitnow job board."""

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
        async def pages() -> AsyncIterator[Page]:
            for number in range(1, MAX_PAGES_PER_STREAM + 1):
                listing: Any = await self._get_json(
                    f"{self.entry.endpoint}?page={number}", per_minute=per_minute
                )
                if not isinstance(listing, dict) or not isinstance(listing.get("data"), list):
                    msg = "The answer does not contain a list of jobs."
                    raise SourceError(SourceErrorClass.INVALID_PAYLOAD, msg)
                candidates: list[Candidate] = []
                skipped = 0
                for job in listing["data"]:
                    try:
                        candidates.append(parse_job(job))
                    except MalformedPostingError:
                        skipped += 1
                links = listing.get("links")
                has_more = bool(isinstance(links, dict) and links.get("next")) and bool(
                    listing["data"]
                )
                yield Page(candidates, skipped=skipped, has_more=has_more)
                if not has_more:
                    return

        return [pages]
