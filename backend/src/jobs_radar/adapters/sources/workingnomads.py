"""Working Nomads job board adapter (ADR-074, research R-00176).

Free public JSON, no key: ``/api/exposed_jobs/`` returns every open posting in one answer, each
with its URL, title, HTML description, company, category, comma-separated tags, a free-text
location and a publication time. There is no identifier (the URL is used) and no pay field. Many
of its postings are independent-contractor work, which the extraction reads from the text.

The feed's ``url`` (``/job/go/<id>/``) only redirects to the employer's application form, so the
page that shows the posting is built from the title and company instead: ``/jobs/<title>-<company>``
(checked against every posting of the feed on 2026-10-14). The feed URL stays the identifier and
the apply link.
"""

import re
import unicodedata
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

_ENTRY = require_entry("workingnomads")


def _text(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _slug(value: str) -> str:
    """Lower-case ASCII words joined by hyphens, as the site writes its page addresses."""
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def parse_job(job: object) -> Candidate:
    """Convert one job object into a candidate; raises :class:`MalformedPostingError`."""
    if not isinstance(job, dict):
        raise MalformedPostingError
    url, title, company = job.get("url"), _text(job.get("title")), _text(job.get("company_name"))
    if not isinstance(url, str) or not url or not title or not company:
        raise MalformedPostingError
    published = job.get("pub_date")
    try:
        posted_at = datetime.fromisoformat(published) if isinstance(published, str) else None
    except ValueError:
        posted_at = None
    if posted_at is not None and posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)
    body = job.get("description")
    category = _text(job.get("category_name"))
    tags = tuple(tag.strip() for tag in _text(job.get("tags")).split(",") if tag.strip())
    eligibility, places = eligibility_from_place_text(_text(job.get("location")))
    # A free-text location is kept as the board wrote it, for the posting detail.
    shown = (_text(job.get("location")),) if _text(job.get("location")) else places
    slug = f"{_slug(title)}-{_slug(company)}"
    posting = SourcePosting(
        external_job_id=url,
        title=title,
        source_url=f"https://www.workingnomads.com/jobs/{slug}",
        apply_url=url,
        description_text=html_to_text(body if isinstance(body, str) else None),
        locations=shown,
        posted_at=posted_at,
        source_updated_at=None,
        departments=(category,) if category else (),
        language=None,
        raw_payload=job,
        company_name=company,
    )
    return Candidate(posting, eligibility, (category, *tags))


class WorkingNomadsAdapter(JobBoardAdapter):
    """Collects the Working Nomads exposed jobs feed."""

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
                try:
                    candidates.append(parse_job(job))
                except MalformedPostingError:
                    skipped += 1
            yield Page(candidates, skipped=skipped)

        return [pages]
