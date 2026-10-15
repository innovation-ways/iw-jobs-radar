"""Remotive job board adapter (ADR-076, research R-00173).

Free public JSON, no key: ``/api/remote-jobs`` returns the board's open postings in one answer
under ``jobs`` (a few dozen; the board delays them by 24 hours). A job has an id, URL, title,
company, category, tags, ``job_type`` (``full_time``, ``contract``, ``freelance``...), a free-text
``candidate_required_location``, a free-text ``salary`` and an HTML description. The board asks
for at most four requests a day and a link back to the posting; the catalogue enforces six hours
between runs.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from jobs_radar.adapters.sources.base import SourceError, SourcePosting
from jobs_radar.adapters.sources.catalogue import require_entry
from jobs_radar.adapters.sources.html_text import html_to_text
from jobs_radar.adapters.sources.job_board import (
    Candidate,
    JobBoardAdapter,
    MalformedPostingError,
    Page,
    Stream,
)
from jobs_radar.adapters.sources.place_text import eligibility_from_place_text
from jobs_radar.domain.enums import SourceErrorClass
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters

_ENTRY = require_entry("remotive")


def _text(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def parse_job(job: object) -> Candidate:
    """Convert one job object into a candidate; raises :class:`MalformedPostingError`."""
    if not isinstance(job, dict):
        raise MalformedPostingError
    raw_id, title = job.get("id"), _text(job.get("title"))
    company, url = _text(job.get("company_name")), job.get("url")
    if raw_id in (None, "") or not title or not company or not isinstance(url, str) or not url:
        raise MalformedPostingError
    published = job.get("publication_date")
    try:
        posted_at = datetime.fromisoformat(published) if isinstance(published, str) else None
    except ValueError:
        posted_at = None
    if posted_at is not None and posted_at.tzinfo is None:
        # The board gives UTC times without an offset.
        posted_at = posted_at.replace(tzinfo=UTC)
    body = job.get("description")
    text = html_to_text(body if isinstance(body, str) else None)
    # The board's own words about contract type and pay are put in the text, where the extraction
    # reads them (the board has no structured field the pipeline could use, ADR-073).
    lines = [text] if text else []
    job_type, salary = _text(job.get("job_type")), _text(job.get("salary"))
    if job_type:
        lines.append(f"Job type stated by the board: {job_type.replace('_', ' ')}")
    if salary:
        lines.append(f"Salary stated by the board: {salary}")
    category = _text(job.get("category"))
    tags = tuple(
        tag.strip() for tag in job.get("tags") or [] if isinstance(tag, str) and tag.strip()
    )
    place = _text(job.get("candidate_required_location"))
    eligibility, places = eligibility_from_place_text(place)
    posting = SourcePosting(
        external_job_id=str(raw_id),
        title=title,
        source_url=url,
        apply_url=url,
        description_text="\n\n".join(lines),
        locations=(place,) if place else places,
        posted_at=posted_at,
        source_updated_at=None,
        departments=(category,) if category else (),
        language=None,
        raw_payload=job,
        company_name=company,
    )
    return Candidate(posting, eligibility, (category, *tags) if category else tags)


class RemotiveAdapter(JobBoardAdapter):
    """Collects the Remotive API."""

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
            answer: Any = await self._get_json(self.entry.endpoint, per_minute=per_minute)
            listing = answer.get("jobs") if isinstance(answer, dict) else None
            if not isinstance(listing, list):
                msg = "The answer does not contain a list of jobs."
                raise SourceError(SourceErrorClass.INVALID_PAYLOAD, msg)
            candidates: list[Candidate] = []
            skipped = 0
            for job in listing:
                try:
                    candidates.append(parse_job(job))
                except MalformedPostingError:
                    skipped += 1
            yield Page(candidates, skipped=skipped)

        return [pages]
