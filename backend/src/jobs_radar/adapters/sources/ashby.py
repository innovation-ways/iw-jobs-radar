"""Ashby public job posting API adapter (ADR-050, research R-00169).

Public and unauthenticated: ``/posting-api/job-board/{name}?includeCompensation=true`` lists every
open posting of one company in a single answer and supports conditional requests (ETag). Postings
the company has not listed publicly (``isListed`` false) are ignored. Ashby publishes no company
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
    clean,
    distinct,
    from_iso,
    guess_company_name,
    invalid,
)
from jobs_radar.adapters.sources.html_text import html_to_text
from jobs_radar.domain.enums import SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.domain.prefilter import PrefilterRules
from jobs_radar.schemas.source_filters import JobBoardFilters

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board"


def _description(job: dict[str, Any]) -> str:
    plain = job.get("descriptionPlain")
    text = (
        plain.strip()
        if isinstance(plain, str) and plain.strip()
        else html_to_text(
            job["descriptionHtml"] if isinstance(job.get("descriptionHtml"), str) else None
        )
    )
    compensation = job.get("compensation")
    summary = (
        clean(compensation.get("compensationTierSummary")) if isinstance(compensation, dict) else ""
    )
    return f"{text}\n\nCompensation: {summary}".strip() if summary else text


def map_posting(job: object) -> SourcePosting:
    """Convert one Ashby posting into a :class:`SourcePosting`."""
    if not isinstance(job, dict):
        raise invalid("A posting in the answer is not an object.")
    raw_id, title, url = job.get("id"), clean(job.get("title")), job.get("jobUrl")
    if raw_id in (None, "") or not title or not isinstance(url, str) or not url:
        raise invalid("A posting in the answer is missing its id, title or address.")
    places = [clean(job.get("location"))]
    for secondary in job.get("secondaryLocations") or []:
        if isinstance(secondary, dict):
            places.append(clean(secondary.get("location")))
    locations = list(distinct(places))
    if job.get("isRemote") is True and not any("remote" in item.lower() for item in locations):
        locations.append("Remote")
    apply_url = job.get("applyUrl")
    return SourcePosting(
        external_job_id=str(raw_id),
        title=title,
        source_url=url,
        apply_url=apply_url if isinstance(apply_url, str) and apply_url else url,
        description_text=_description(job),
        locations=tuple(locations),
        posted_at=from_iso(job.get("publishedAt")),
        source_updated_at=None,
        departments=distinct([clean(job.get("department")), clean(job.get("team"))]),
        language=None,
        raw_payload=job,
    )


class AshbyAdapter(CompanyBoardAdapter):
    """Collects public Ashby company boards."""

    source_type = SourceType.ASHBY
    base_url = BASE_URL

    def _url(self, identifier: str) -> str:
        return f"{self.endpoint(identifier)}?includeCompensation=true"

    @staticmethod
    def _listed(listing: Any) -> list[Any]:
        if not isinstance(listing, dict) or not isinstance(listing.get("jobs"), list):
            raise invalid("The answer does not contain a list of postings.")
        return [
            job
            for job in listing["jobs"]
            if not (isinstance(job, dict) and job.get("isListed") is False)
        ]

    async def validate(
        self,
        identifier: str,
        credential: str | None = None,
        filters: JobBoardFilters | None = None,
        scope: LocationScope | None = None,
        rules: PrefilterRules | None = None,
    ) -> BoardInfo:
        """Check that the company has a board and count its listed postings."""
        response = await self._get(self._url(identifier), identifier, per_minute=6)
        count = len(self._listed(self._json(response)))
        return BoardInfo(name=guess_company_name(identifier), postings_count=count)

    async def collect(self, checkpoint: SourceCheckpoint) -> CollectionResult:
        """Fetch every listed posting, or report that nothing changed since ``checkpoint.etag``."""
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
        postings = tuple(map_posting(job) for job in self._listed(self._json(response)))
        return CollectionResult(
            "modified", postings, etag, response.status, duration_ms, len(postings)
        )
