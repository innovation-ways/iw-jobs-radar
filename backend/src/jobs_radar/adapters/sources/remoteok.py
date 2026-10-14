"""Remote OK job board adapter (ADR-074, research R-00176).

Free public JSON, no key: ``/api`` returns about a hundred of the newest postings as one array.
The first element is a legal notice (link back to Remote OK, do not use its logo), not a job. A job
has an id, company, position, tags, HTML description, a free-text location and ``salary_min`` /
``salary_max`` (annual, ``0`` when not stated; no currency is given). The contract type appears only
in the text, which the extraction reads.
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

_ENTRY = require_entry("remoteok")


def _text(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _salary_line(job: dict[str, Any]) -> str:
    low, high = job.get("salary_min"), job.get("salary_max")
    values = [v for v in (low, high) if isinstance(v, int | float) and v > 0]
    if not values:
        return ""
    amount = "-".join(f"{value:g}" for value in dict.fromkeys(values))
    return f"Annual salary range stated by the board (currency not given): {amount}"


def parse_job(job: object) -> Candidate:
    """Convert one job object into a candidate; raises :class:`MalformedPostingError`."""
    if not isinstance(job, dict):
        raise MalformedPostingError
    raw_id, title = job.get("id"), _text(job.get("position"))
    company, url = _text(job.get("company")), job.get("url")
    if raw_id in (None, "") or not title or not company or not isinstance(url, str) or not url:
        raise MalformedPostingError
    published = job.get("date")
    try:
        posted_at = datetime.fromisoformat(published) if isinstance(published, str) else None
    except ValueError:
        posted_at = None
    if posted_at is not None and posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)
    body = job.get("description")
    text = html_to_text(body if isinstance(body, str) else None)
    salary = _salary_line(job)
    tags = tuple(
        tag.strip() for tag in job.get("tags") or [] if isinstance(tag, str) and tag.strip()
    )
    eligibility, places = eligibility_from_place_text(_text(job.get("location")))
    apply_url = job.get("apply_url")
    posting = SourcePosting(
        external_job_id=str(raw_id),
        title=title,
        source_url=url,
        apply_url=apply_url if isinstance(apply_url, str) and apply_url else url,
        description_text=f"{text}\n\n{salary}".strip() if salary else text,
        locations=places,
        posted_at=posted_at,
        source_updated_at=None,
        departments=(),
        language=None,
        raw_payload=job,
        company_name=company,
    )
    return Candidate(posting, eligibility, tags)


class RemoteOkAdapter(JobBoardAdapter):
    """Collects the Remote OK API."""

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
            listing: Any = await self._get_json(self.entry.endpoint, per_minute=per_minute)
            if not isinstance(listing, list):
                msg = "The answer does not contain a list of jobs."
                raise SourceError(SourceErrorClass.INVALID_PAYLOAD, msg)
            candidates: list[Candidate] = []
            skipped = 0
            for job in listing:
                # The first element is the legal notice, not a posting.
                if isinstance(job, dict) and "legal" in job and "id" not in job:
                    continue
                try:
                    candidates.append(parse_job(job))
                except MalformedPostingError:
                    skipped += 1
            yield Page(candidates, skipped=skipped)

        return [pages]
