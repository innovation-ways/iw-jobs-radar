"""Lever Postings API adapter (ADR-050, research R-00169).

Public and unauthenticated: ``/v0/postings/{company}?mode=json`` lists every open posting of one
company in a single answer and supports conditional requests (ETag). Lever publishes no company
name, so the display name is guessed from the identifier (the owner may type the real one).
"""

import asyncio
from typing import Any

from jobs_radar.adapters.sources.base import (
    BoardInfo,
    CollectionResult,
    SourceCheckpoint,
    SourcePosting,
)
from jobs_radar.adapters.sources.company_board import (
    CompanyBoardAdapter,
    as_dict,
    clean,
    distinct,
    from_millis,
    guess_company_name,
    invalid,
)
from jobs_radar.adapters.sources.html_text import html_to_text
from jobs_radar.domain.enums import SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.domain.prefilter import PrefilterRules
from jobs_radar.schemas.source_filters import JobBoardFilters

BASE_URL = "https://api.lever.co/v0/postings"


def _description(job: dict[str, Any]) -> str:
    """Return the text of a posting: the opening, each titled list, then the closing note."""
    opening = job.get("descriptionPlain")
    parts = [
        opening.strip()
        if isinstance(opening, str) and opening.strip()
        else html_to_text(job["description"] if isinstance(job.get("description"), str) else None)
    ]
    for block in job.get("lists") or []:
        if isinstance(block, dict):
            title = clean(block.get("text"))
            body = html_to_text(block["content"] if isinstance(block.get("content"), str) else None)
            parts.append("\n".join(part for part in (title, body) if part))
    closing = job.get("additionalPlain")
    if isinstance(closing, str) and closing.strip():
        parts.append(closing.strip())
    return "\n\n".join(part for part in parts if part)


def map_posting(job: object) -> SourcePosting:
    """Convert one Lever posting into a :class:`SourcePosting`."""
    if not isinstance(job, dict):
        raise invalid("A posting in the answer is not an object.")
    raw_id, title, url = job.get("id"), clean(job.get("text")), job.get("hostedUrl")
    if raw_id in (None, "") or not title or not isinstance(url, str) or not url:
        raise invalid("A posting in the answer is missing its id, title or address.")
    categories = as_dict(job.get("categories"))
    places = categories.get("allLocations")
    places = (
        [clean(item) for item in places]
        if isinstance(places, list)
        else [clean(categories.get("location"))]
    )
    locations = list(distinct(places))
    if job.get("workplaceType") == "remote" and not any(
        "remote" in item.lower() for item in locations
    ):
        locations.append("Remote")
    apply_url = job.get("applyUrl")
    return SourcePosting(
        external_job_id=str(raw_id),
        title=title,
        source_url=url,
        apply_url=apply_url if isinstance(apply_url, str) and apply_url else url,
        description_text=_description(job),
        locations=tuple(locations),
        posted_at=from_millis(job.get("createdAt")),
        source_updated_at=None,
        departments=distinct([clean(categories.get("department")), clean(categories.get("team"))]),
        language=None,
        raw_payload=job,
    )


class LeverAdapter(CompanyBoardAdapter):
    """Collects public Lever company boards."""

    source_type = SourceType.LEVER
    base_url = BASE_URL

    def _url(self, identifier: str) -> str:
        return f"{self.endpoint(identifier)}?mode=json"

    def _postings(self, listing: Any) -> list[Any]:
        if not isinstance(listing, list):
            raise invalid("The answer does not contain a list of postings.")
        return listing

    async def validate(
        self,
        identifier: str,
        credential: str | None = None,
        filters: JobBoardFilters | None = None,
        scope: LocationScope | None = None,
        rules: PrefilterRules | None = None,
    ) -> BoardInfo:
        """Check that the company has a board and count its postings."""
        response = await self._get(self._url(identifier), identifier, per_minute=6)
        count = len(self._postings(self._json(response)))
        return BoardInfo(name=guess_company_name(identifier), postings_count=count)

    async def collect(self, checkpoint: SourceCheckpoint) -> CollectionResult:
        """Fetch every open posting, or report that nothing changed since ``checkpoint.etag``."""
        started = asyncio.get_running_loop().time()
        response = await self._get(
            self._url(checkpoint.identifier),
            checkpoint.identifier,
            checkpoint.rate_limit_per_minute,
            checkpoint.etag,
        )
        duration_ms = int((asyncio.get_running_loop().time() - started) * 1000)
        etag = response.headers.get("etag") or checkpoint.etag
        if response.status == 304:
            return CollectionResult("not_modified", (), etag, 304, duration_ms, None)
        postings = tuple(map_posting(job) for job in self._postings(self._json(response)))
        return CollectionResult(
            "modified", postings, etag, response.status, duration_ms, len(postings)
        )
