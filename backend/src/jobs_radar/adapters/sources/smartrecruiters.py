"""SmartRecruiters Posting API adapter (ADR-050, research R-00169).

Public and unauthenticated: ``/v1/companies/{company}/postings`` lists postings page by page
(without their text) and ``/postings/{id}`` gives each posting's description. A large company has
thousands of postings, so the adapter reads the details only of postings that look technical (the
posting's own function, or a technology word in the title) and at most ``max_details`` per run;
a run that stops at that limit is reported as truncated and never closes postings. SmartRecruiters
answers 200 with no postings for an unknown company, so a company without postings cannot be added.
"""

import asyncio
from typing import Any

from jobs_radar.adapters.sources.base import (
    BoardInfo,
    CollectionResult,
    SourceCheckpoint,
    SourceError,
    SourcePosting,
)
from jobs_radar.adapters.sources.company_board import (
    CompanyBoardAdapter,
    as_dict,
    clean,
    distinct,
    from_iso,
    invalid,
)
from jobs_radar.adapters.sources.html_text import html_to_text
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import LocationScope, categorise
from jobs_radar.schemas.source_filters import JobBoardFilters

BASE_URL = "https://api.smartrecruiters.com/v1/companies"
PAGE_SIZE = 100
MAX_PAGES = 100
DEFAULT_MAX_DETAILS = 200
# SmartRecruiters' own "function" values for technology work.
_TECH_FUNCTIONS = frozenset({"information_technology", "engineering"})
_SECTIONS = ("jobDescription", "qualifications", "additionalInformation")


def _looks_technical(item: dict[str, Any]) -> bool:
    function = as_dict(item.get("function"))
    if function.get("id") in _TECH_FUNCTIONS:
        return True
    return bool(categorise([clean(item.get("name")), clean(function.get("label"))]))


def _description(detail: dict[str, Any]) -> str:
    job_ad = as_dict(detail.get("jobAd"))
    sections = as_dict(job_ad.get("sections"))
    parts: list[str] = []
    for key in _SECTIONS:
        section = sections.get(key)
        if isinstance(section, dict) and isinstance(section.get("text"), str):
            text = html_to_text(section["text"])
            title = clean(section.get("title"))
            if text:
                parts.append("\n".join(part for part in (title, text) if part))
    return "\n\n".join(parts)


def map_posting(detail: object) -> SourcePosting:
    """Convert one SmartRecruiters posting detail into a :class:`SourcePosting`."""
    if not isinstance(detail, dict):
        raise invalid("A posting in the answer is not an object.")
    raw_id, name = detail.get("id"), clean(detail.get("name"))
    url = detail.get("postingUrl") or detail.get("applyUrl")
    if raw_id in (None, "") or not name or not isinstance(url, str) or not url:
        raise invalid("A posting in the answer is missing its id, title or address.")
    place = as_dict(detail.get("location"))
    places = [clean(place.get("fullLocation")) or clean(place.get("city"))]
    if place.get("remote") is True:
        places.append("Remote")
    elif place.get("hybrid") is True:
        places.append("Hybrid")
    function = as_dict(detail.get("function"))
    department = as_dict(detail.get("department"))
    language = as_dict(detail.get("language"))
    code = language.get("code")
    apply_url = detail.get("applyUrl")
    return SourcePosting(
        external_job_id=str(raw_id),
        title=name,
        source_url=url,
        apply_url=apply_url if isinstance(apply_url, str) and apply_url else url,
        description_text=_description(detail),
        locations=distinct(places),
        posted_at=from_iso(detail.get("releasedDate")),
        source_updated_at=None,
        departments=distinct([clean(function.get("label")), clean(department.get("label"))]),
        language=code if isinstance(code, str) and code else None,
        raw_payload=detail,
    )


class SmartRecruitersAdapter(CompanyBoardAdapter):
    """Collects public SmartRecruiters company boards."""

    source_type = SourceType.SMARTRECRUITERS
    base_url = BASE_URL

    def __init__(self, *args: Any, max_details: int = DEFAULT_MAX_DETAILS, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._max_details = max_details

    def endpoint(self, identifier: str) -> str:
        """Return the postings URL stored in the source configuration."""
        return f"{self.base_url}/{self._token(identifier)}/postings"

    @staticmethod
    def _content(listing: Any) -> list[Any]:
        if not isinstance(listing, dict) or not isinstance(listing.get("content"), list):
            raise invalid("The answer does not contain a list of postings.")
        content: list[Any] = listing["content"]
        return content

    async def validate(
        self,
        identifier: str,
        credential: str | None = None,
        filters: JobBoardFilters | None = None,
        scope: LocationScope | None = None,
    ) -> BoardInfo:
        """Check that the company has postings (an unknown company looks like an empty one)."""
        listing = self._json(await self._get(f"{self.endpoint(identifier)}?limit=1", identifier, 6))
        content = self._content(listing)
        total = listing.get("totalFound")
        if not content or not isinstance(total, int) or total < 1:
            msg = "No open postings were found for this company identifier."
            raise SourceError(SourceErrorClass.NOT_FOUND, msg, http_status=200)
        company = content[0].get("company") if isinstance(content[0], dict) else None
        name = clean(company.get("name")) if isinstance(company, dict) else ""
        return BoardInfo(name=name or identifier, postings_count=total)

    async def collect(self, checkpoint: SourceCheckpoint) -> CollectionResult:
        """List the postings, then read the details of the technical ones (up to the limit)."""
        started = asyncio.get_running_loop().time()
        identifier, per_minute = checkpoint.identifier, checkpoint.rate_limit_per_minute
        base = self.endpoint(identifier)
        wanted: list[str] = []
        dropped = 0
        declared: int | None = None
        offset = 0
        for _ in range(MAX_PAGES):
            listing = self._json(
                await self._get(f"{base}?limit={PAGE_SIZE}&offset={offset}", identifier, per_minute)
            )
            content = self._content(listing)
            total = listing.get("totalFound")
            declared = total if isinstance(total, int) else declared
            for item in content:
                if isinstance(item, dict) and item.get("id") and _looks_technical(item):
                    wanted.append(str(item["id"]))
                else:
                    dropped += 1
            offset += len(content)
            if len(wanted) > self._max_details:
                break  # more are known than can be read: the rest need not even be listed
            if not content or declared is None or offset >= declared:
                break
        truncated = len(wanted) > self._max_details
        postings: list[SourcePosting] = []
        for posting_id in wanted[: self._max_details]:
            try:
                detail = self._json(await self._get(f"{base}/{posting_id}", identifier, per_minute))
            except SourceError as error:
                if error.error_class is SourceErrorClass.NOT_FOUND:
                    dropped += 1  # closed between the list and the detail
                    continue
                raise
            postings.append(map_posting(detail))
        duration_ms = int((asyncio.get_running_loop().time() - started) * 1000)
        return CollectionResult(
            "modified",
            tuple(postings),
            None,
            200,
            duration_ms,
            declared,
            dropped_count=dropped,
            truncated=truncated,
        )
