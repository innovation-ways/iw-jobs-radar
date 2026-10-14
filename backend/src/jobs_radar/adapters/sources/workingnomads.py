"""Working Nomads job board adapter (ADR-074, research R-00176).

Free public JSON, no key: ``/api/exposed_jobs/`` returns every open posting in one answer, each
with its URL, title, HTML description, company, category, comma-separated tags, a free-text
location and a publication time. There is no identifier (the URL is used) and no pay field. Many
of its postings are independent-contractor work, which the extraction reads from the text.

The feed's ``url`` (``/job/go/<id>/``) only redirects to the employer's application form, so the
page that shows the posting is ``/jobs?job=<slug>``. The slug is the site's own and cannot be
derived from the title (owner, 2026-10-14: ADR-074 amendment); the site's search endpoint, which
its own pages use, returns it, so one request asks for the slugs of the whole feed. If that
request fails the run goes on and the posting keeps the feed address. The feed URL stays the
identifier and the apply link.
"""

import re
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

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


_FEED_ID = re.compile(r"/job/go/(\d+)/?$")
_SEARCH = "https://www.workingnomads.com/jobsapi/_search"
_PAGE = "https://www.workingnomads.com/jobs?job="
# A search answer holds at most this many hits; the feed has about fifty postings.
_LOOKUP_SIZE = 200


def _feed_id(url: str) -> str | None:
    """Return the numeric id inside a feed address, or ``None`` if it has another shape."""
    match = _FEED_ID.search(url)
    return match.group(1) if match else None


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
    posting = SourcePosting(
        external_job_id=url,
        title=title,
        # The page address needs the site's slug, added later by one lookup (see the module doc).
        source_url=url,
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


def _with_page(candidate: Candidate, slugs: dict[str, str]) -> Candidate:
    """Point the candidate at its posting page when the site gave its slug."""
    feed_id = _feed_id(candidate.posting.external_job_id)
    slug = slugs.get(feed_id) if feed_id is not None else None
    if not slug:
        return candidate
    posting = replace(candidate.posting, source_url=_PAGE + slug)
    return replace(candidate, posting=posting)


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
            slugs = await self._slugs(candidates, per_minute)
            yield Page([_with_page(candidate, slugs) for candidate in candidates], skipped=skipped)

        return [pages]

    async def _slugs(self, candidates: list[Candidate], per_minute: int) -> dict[str, str]:
        """Ask the site for the page slug of every posting; an unusable answer gives none."""
        ids = sorted(
            {i for c in candidates if (i := _feed_id(c.posting.external_job_id)) is not None}
        )
        if not ids:
            return {}
        query = quote("_id:(" + " OR ".join(ids) + ")")
        url = f"{_SEARCH}?size={_LOOKUP_SIZE}&_source=id,slug&q={query}"
        try:
            answer: Any = await self._get_json(url, per_minute=per_minute)
        # Intentionally broad: the slug only improves the link, so any failure of this one extra
        # request must not fail the collection run (the posting keeps the feed address).
        except Exception:
            return {}
        hits = answer.get("hits", {}).get("hits", []) if isinstance(answer, dict) else []
        slugs: dict[str, str] = {}
        for hit in hits if isinstance(hits, list) else []:
            source = hit.get("_source") if isinstance(hit, dict) else None
            if (
                isinstance(source, dict)
                and isinstance(source.get("slug"), str)
                and source.get("id")
            ):
                slugs[str(source["id"])] = source["slug"]
        return slugs
