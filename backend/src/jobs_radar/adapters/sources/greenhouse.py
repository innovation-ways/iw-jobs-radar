"""Greenhouse Job Board API adapter (ADR-015, research R-00169, document 13 section 5.1).

The API is public and unauthenticated. One board per company: ``/v1/boards/{token}/jobs``. The
adapter validates tokens, sends conditional requests (``If-None-Match``), spaces and retries
requests within strict bounds, and classifies every failure (:class:`SourceErrorClass`).
"""

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

from jobs_radar.adapters.sources.base import (
    BoardInfo,
    CollectionResult,
    RateLimiter,
    SourceCheckpoint,
    SourceError,
    SourcePosting,
)
from jobs_radar.adapters.sources.html_text import html_to_text
from jobs_radar.adapters.sources.polite_http import PoliteGetter
from jobs_radar.core.http import GuardedHttpClient, HttpResponse
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def _invalid(message: str) -> SourceError:
    return SourceError(SourceErrorClass.INVALID_PAYLOAD, message)


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _clean(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _locations(job: dict[str, Any]) -> tuple[str, ...]:
    """Return the location string then office locations, without case-insensitive duplicates."""
    candidates: list[str] = []
    location = job.get("location")
    if isinstance(location, dict):
        candidates.append(_clean(location.get("name")))
    for office in job.get("offices") or []:
        if isinstance(office, dict):
            candidates.append(_clean(office.get("location")) or _clean(office.get("name")))
    seen: set[str] = set()
    result: list[str] = []
    for candidate in candidates:
        if candidate and candidate.lower() not in seen:
            seen.add(candidate.lower())
            result.append(candidate)
    return tuple(result)


def map_job(job: object) -> SourcePosting:
    """Convert one Greenhouse job object into a :class:`SourcePosting`."""
    if not isinstance(job, dict):
        raise _invalid("A job in the answer is not an object.")
    raw_id, title, url = job.get("id"), _clean(job.get("title")), job.get("absolute_url")
    if raw_id in (None, "") or not title or not isinstance(url, str) or not url:
        raise _invalid("A job in the answer is missing its id, title or address.")
    departments = tuple(
        _clean(item.get("name"))
        for item in job.get("departments") or []
        if isinstance(item, dict) and _clean(item.get("name"))
    )
    language = job.get("language")
    return SourcePosting(
        external_job_id=str(raw_id),
        title=title,
        source_url=url,
        apply_url=url,
        description_text=html_to_text(
            job.get("content") if isinstance(job.get("content"), str) else None
        ),
        locations=_locations(job),
        posted_at=_parse_time(job.get("first_published")),
        source_updated_at=_parse_time(job.get("updated_at")),
        departments=departments,
        language=language if isinstance(language, str) and language else None,
        raw_payload=job,
    )


class GreenhouseAdapter:
    """Collects public Greenhouse job boards."""

    source_type = SourceType.GREENHOUSE

    def __init__(
        self,
        client: GuardedHttpClient,
        *,
        sleep: Any = asyncio.sleep,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._getter = PoliteGetter(
            client,
            sleep=sleep,
            limiter=limiter,
            not_found_message="The board was not found. Check the board token.",
        )

    def endpoint(self, identifier: str) -> str:
        """Return the jobs endpoint stored in the source configuration."""
        return f"{BASE_URL}/{self._token(identifier)}/jobs"

    @staticmethod
    def _token(identifier: str) -> str:
        if not _TOKEN.match(identifier):
            msg = "A board token may only contain letters, digits, hyphens and underscores."
            raise SourceError(SourceErrorClass.CONFIGURATION, msg)
        return identifier

    async def validate(
        self,
        identifier: str,
        credential: str | None = None,
        filters: JobBoardFilters | None = None,
        scope: LocationScope | None = None,
    ) -> BoardInfo:
        """Check the board exists and return its name and number of postings."""
        token = self._token(identifier)
        board = self._json(await self._get(f"{BASE_URL}/{token}", {}, token, per_minute=6))
        name = _clean(board.get("name")) if isinstance(board, dict) else ""
        if not name:
            raise _invalid("The board has no name.")
        listing = self._json(await self._get(f"{BASE_URL}/{token}/jobs", {}, token, per_minute=6))
        jobs = self._jobs(listing)
        total = (
            listing.get("meta", {}).get("total") if isinstance(listing.get("meta"), dict) else None
        )
        return BoardInfo(name=name, postings_count=total if isinstance(total, int) else len(jobs))

    async def collect(self, checkpoint: SourceCheckpoint) -> CollectionResult:
        """Fetch all current postings, or report that nothing changed since ``checkpoint.etag``."""
        token = self._token(checkpoint.identifier)
        headers = {"If-None-Match": checkpoint.etag} if checkpoint.etag else {}
        started = asyncio.get_running_loop().time()
        response = await self._get(
            f"{BASE_URL}/{token}/jobs?content=true",
            headers,
            token,
            per_minute=checkpoint.rate_limit_per_minute,
        )
        duration_ms = int((asyncio.get_running_loop().time() - started) * 1000)
        etag = response.headers.get("etag") or checkpoint.etag
        if response.status == 304:
            return CollectionResult("not_modified", (), etag, 304, duration_ms, None)
        listing = self._json(response)
        postings = tuple(map_job(job) for job in self._jobs(listing))
        meta = listing.get("meta")
        total = meta.get("total") if isinstance(meta, dict) else None
        return CollectionResult(
            "modified",
            postings,
            etag,
            response.status,
            duration_ms,
            total if isinstance(total, int) else None,
        )

    # --- HTTP -----------------------------------------------------------------------------------

    async def _get(
        self, url: str, headers: dict[str, str], key: str, *, per_minute: int
    ) -> HttpResponse:
        """GET with rate limiting and bounded retries (see :class:`PoliteGetter`)."""
        return await self._getter.get(url, headers, key, per_minute=per_minute)

    # --- payload parsing --------------------------------------------------------------------

    @staticmethod
    def _json(response: HttpResponse) -> Any:
        try:
            return json.loads(response.body)
        except (ValueError, UnicodeDecodeError) as exc:
            msg = "The answer is not valid JSON."
            raise _invalid(msg) from exc

    @staticmethod
    def _jobs(listing: Any) -> list[Any]:
        if not isinstance(listing, dict) or not isinstance(listing.get("jobs"), list):
            raise _invalid("The answer does not contain a list of jobs.")
        jobs: list[Any] = listing["jobs"]
        return jobs
