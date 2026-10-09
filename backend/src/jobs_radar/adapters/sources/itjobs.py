"""ITJobs.pt job board adapter (ADR-049, T9.6, research R-00173).

ITJobs.pt, the Portuguese IT job board, offers a read-only API (``job/list.json``) with a free key
that the owner requests by email and enters in the Sources screen. The key travels as the
``api_key`` query parameter, so it is masked wherever a URL could be logged and never stored in the
source URL. The response shape follows the public documentation; it has not yet been checked
against the live service with a real key, so every field is read defensively and a surprise is
reported as ``invalid_payload`` instead of guessed.

ITJobs.pt does not document the numeric ``workModel``, so remote work is recognised from the words
"remote" or "remoto" in the title, places or text; a posting that does not say so is treated as
on-site and judged by the owner's radius when its place can be read.
"""

import re
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlencode

from jobs_radar.adapters.sources.base import SourceError, SourcePosting
from jobs_radar.adapters.sources.catalogue import require_entry
from jobs_radar.adapters.sources.company_board import as_dict, clean, distinct, from_iso
from jobs_radar.adapters.sources.countries import place_coordinates
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
from jobs_radar.domain.job_board_rules import Eligibility, LocationScope, Reach
from jobs_radar.schemas.source_filters import JobBoardFilters

_ENTRY = require_entry("itjobs_pt")
_PAGE_SIZE = 100
_REMOTE = re.compile(r"\b(remote|remoto|remota|teletrabalho|home office)\b", re.IGNORECASE)


def _names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return distinct([clean(as_dict(item).get("name")) for item in value])


def _salary_line(job: dict[str, Any]) -> str:
    low, high = job.get("salaryMin"), job.get("salaryMax")
    parts = [f"{value:g}" for value in (low, high) if isinstance(value, int | float) and value]
    if not parts:
        return ""
    # The currency and the period are not stated by the API, so they are not guessed.
    return f"Salary range stated by the board: {'-'.join(parts)} (currency and period not stated)"


def parse_job(job: object) -> Candidate:
    """Convert one ITJobs.pt posting into a candidate; raises :class:`MalformedPostingError`."""
    if not isinstance(job, dict):
        raise MalformedPostingError
    raw_id, title = job.get("id"), clean(job.get("title"))
    company = clean(as_dict(job.get("company")).get("name"))
    if raw_id in (None, "") or not title or not company:
        raise MalformedPostingError
    slug = clean(job.get("slug"))
    # The public page of an offer; the API itself documents no link.
    url = (
        f"https://www.itjobs.pt/oferta/{raw_id}/{slug}"
        if slug
        else f"https://www.itjobs.pt/oferta/{raw_id}"
    )
    places = _names(job.get("locations"))
    body = html_to_text(job["body"] if isinstance(job.get("body"), str) else None)
    remote = bool(_REMOTE.search(" ".join((title, *places, body))))
    place = None
    if not remote:
        for name in places:
            place = place_coordinates(name)
            if place:
                break
    salary = _salary_line(job)
    types = _names(job.get("types"))
    posting = SourcePosting(
        external_job_id=str(raw_id),
        title=title,
        source_url=url,
        apply_url=url,
        description_text=f"{body}\n\n{salary}".strip() if salary else body,
        locations=places,
        posted_at=from_iso(job.get("publishedAt")),
        source_updated_at=from_iso(job.get("updatedAt")),
        departments=types,
        language="pt",
        raw_payload=job,
        company_name=company,
    )
    # Every posting is in Portugal, so remote work is open from Portugal.
    return Candidate(
        posting,
        Eligibility(Reach.COUNTRIES, frozenset({"PT"})),
        (*types,),
        remote=remote,
        place=place,
    )


class ItJobsAdapter(JobBoardAdapter):
    """Collects the ITJobs.pt job board with the owner's key."""

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
        if not credential:
            msg = "ITJobs.pt needs its API key."
            raise SourceError(SourceErrorClass.AUTHENTICATION, msg)

        async def pages() -> AsyncIterator[Page]:
            for number in range(1, MAX_PAGES_PER_STREAM + 1):
                query = {"api_key": credential, "limit": _PAGE_SIZE, "page": number}
                listing: Any = await self._get_json(
                    f"{self.entry.endpoint}?{urlencode(query)}", per_minute=per_minute
                )
                if isinstance(listing, dict) and "error" in listing and "results" not in listing:
                    msg = "The source refused the credential."
                    raise SourceError(SourceErrorClass.AUTHENTICATION, msg)
                if not isinstance(listing, dict) or not isinstance(listing.get("results"), list):
                    msg = "The answer does not contain a list of jobs."
                    raise SourceError(SourceErrorClass.INVALID_PAYLOAD, msg)
                candidates: list[Candidate] = []
                skipped = 0
                for job in listing["results"]:
                    try:
                        candidates.append(parse_job(job))
                    except MalformedPostingError:
                        skipped += 1
                total, used = listing.get("total"), listing.get("limit")
                total = total if isinstance(total, int) else None
                size = used if isinstance(used, int) and used > 0 else _PAGE_SIZE
                has_more = bool(listing["results"]) and total is not None and number * size < total
                yield Page(
                    candidates,
                    skipped=skipped,
                    has_more=has_more,
                    declared_total=total if number == 1 else None,
                )
                if not has_more:
                    return

        return [pages]
