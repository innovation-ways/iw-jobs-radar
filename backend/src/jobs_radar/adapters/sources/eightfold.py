"""Eightfold careers-site adapter (ADR-055).

Many large employers (Amdocs, Vodafone, Ericsson, ...) publish their vacancies on an Eightfold
careers site such as ``jobs.amdocs.com``. The site's own pages call a public, unauthenticated JSON
API: ``/api/pcsx/search`` lists postings ten at a time (without their text) and
``/api/pcsx/position_details`` gives one posting with its description. The API is not documented,
so every answer is checked and a changed shape fails visibly instead of storing bad data.

The identifier is the careers host (``jobs.amdocs.com``); the company domain the API needs is the
host without its first label (``amdocs.com``). A large company has thousands of postings, so the
adapter lists newest first, reads the details of at most ``max_details`` postings per run and
reports a run that stopped there (or at the page limit) as truncated, which never closes postings.
"""

import asyncio
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

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
    guess_company_name,
    invalid,
)
from jobs_radar.adapters.sources.countries import country_name
from jobs_radar.adapters.sources.html_text import html_to_text
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import LocationScope, categorise
from jobs_radar.schemas.source_filters import JobBoardFilters

DEFAULT_MAX_DETAILS = 200
# The API lists ten postings a page, so this reads up to 2,000 postings of a listing.
DEFAULT_MAX_PAGES = 200
# Three or more DNS labels, each letters, digits or inner hyphens (the host becomes part of a URL).
_HOST = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?){2,}$"
)
_MODES = {"hybrid": "Hybrid", "remote": "Remote"}
# Eightfold's "remote_local" is remote work inside the posting's own country, so it is written as
# the text the pre-filter reads (``Remote - PT``); a plain "remote" has no country limit.
_COUNTRY_TAIL = re.compile(r"(?:^|[\s,])([A-Z]{2})$")
# Search term that lists the remote postings of the whole site, whatever their country.
REMOTE_LISTING = "Remote"


def _not_an_eightfold_site() -> SourceError:
    return SourceError(
        SourceErrorClass.NOT_FOUND,
        "This address does not look like an Eightfold careers site. Check the identifier.",
    )


def _posted_at(value: object) -> datetime | None:
    """Return the UTC time of a timestamp in seconds, or ``None``."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, UTC)
    return None


def _remote_places(standardised: object) -> list[str]:
    """Remote places for a posting: one ``Remote - XX`` per country, or plain ``Remote``."""
    codes: list[str] = []
    for place in standardised if isinstance(standardised, list) else []:
        match = _COUNTRY_TAIL.search(clean(place))
        if match:
            codes.append(match.group(1))
    return [f"Remote - {code}" for code in dict.fromkeys(codes)] or ["Remote"]


def map_posting(detail: object, host: str) -> SourcePosting:
    """Convert one Eightfold position detail into a :class:`SourcePosting`."""
    if not isinstance(detail, dict):
        raise invalid("A posting in the answer is not an object.")
    raw_id, title = detail.get("id"), clean(detail.get("name"))
    public_url, path = detail.get("publicUrl"), detail.get("positionUrl")
    # The address is the one the site publishes, but only over HTTPS and never trusted blindly.
    if isinstance(public_url, str) and public_url.startswith("https://"):
        url = public_url
    elif isinstance(path, str) and path.startswith("/"):
        url = f"https://{host}{path}"
    else:
        url = ""
    if raw_id in (None, "") or not title or not url:
        raise invalid("A posting in the answer is missing its id, title or address.")
    places = detail.get("locations")
    locations = [clean(item) for item in places] if isinstance(places, list) else []
    option = str(detail.get("workLocationOption") or "").lower()
    if option == "remote_local":
        locations.extend(_remote_places(detail.get("standardizedLocations")))
    elif option in _MODES:
        locations.append(_MODES[option])
    return SourcePosting(
        external_job_id=str(raw_id),
        title=title,
        source_url=url,
        apply_url=url,
        description_text=html_to_text(
            detail["jobDescription"] if isinstance(detail.get("jobDescription"), str) else None
        ),
        locations=distinct(locations),
        posted_at=_posted_at(detail.get("postedTs")),
        source_updated_at=None,
        departments=distinct([clean(detail.get("department"))]),
        language=None,
        raw_payload=detail,
    )


class EightfoldAdapter(CompanyBoardAdapter):
    """Collects the public postings of one Eightfold careers site."""

    source_type = SourceType.EIGHTFOLD
    base_url = ""

    def __init__(
        self,
        *args: Any,
        max_details: int = DEFAULT_MAX_DETAILS,
        max_pages: int = DEFAULT_MAX_PAGES,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._max_details = max_details
        self._max_pages = max_pages

    @staticmethod
    def _parts(identifier: str) -> tuple[str, str]:
        """Return the careers host and the company domain the API needs."""
        host = identifier.strip().lower()
        if not _HOST.match(host):
            msg = (
                "The identifier must be the address of the careers site, such as jobs.example.com."
            )
            raise SourceError(SourceErrorClass.CONFIGURATION, msg)
        return host, host.split(".", 1)[1]

    def endpoint(self, identifier: str) -> str:
        """Return the search address stored in the source configuration."""
        return f"https://{self._parts(identifier)[0]}/api/pcsx/search"

    def _search_url(self, host: str, domain: str, start: int, country: str | None) -> str:
        query = {"domain": domain, "query": "", "start": start, "sort_by": "timestamp"}
        if country:
            query["location"] = country
        return f"https://{host}/api/pcsx/search?{urlencode(query)}"

    @staticmethod
    def _listing(answer: Any, *, probing: bool = False) -> tuple[list[Any], int]:
        """Return the positions and the total of one search answer, or refuse its shape."""
        data = answer.get("data") if isinstance(answer, dict) else None
        if not isinstance(data, dict):
            # An unknown company domain answers {"message": "Not authorized for PCSX"}.
            if probing:
                raise _not_an_eightfold_site()
            raise invalid("The answer does not contain a list of postings.")
        positions, count = data.get("positions"), data.get("count")
        if not isinstance(positions, list) or not isinstance(count, int):
            raise invalid("The answer does not contain a list of postings.")
        return positions, count

    async def validate(
        self,
        identifier: str,
        credential: str | None = None,
        filters: JobBoardFilters | None = None,
        scope: LocationScope | None = None,
    ) -> BoardInfo:
        """Check that the site is an Eightfold careers site with postings."""
        host, domain = self._parts(identifier)
        answer = self._json(await self._get(self._search_url(host, domain, 0, None), host, 6))
        _, count = self._listing(answer, probing=True)
        if count < 1:
            msg = "No open postings were found on this careers site."
            raise SourceError(SourceErrorClass.NOT_FOUND, msg, http_status=200)
        return BoardInfo(name=guess_company_name(domain.split(".")[0]), postings_count=count)

    @staticmethod
    def _countries(scope: LocationScope | None) -> list[str | None]:
        """Country names to list, or ``[None]`` for the whole site when the scope is unknown."""
        if scope is None or scope.any_country or not scope.country_codes:
            return [None]
        names = [country_name(code) for code in sorted(scope.country_codes)]
        # The remote postings are listed too: a posting open to the owner's country need not be
        # located there. Each one says which country it is open to, and the pre-filter decides.
        return [*[name for name in names if name], REMOTE_LISTING] if any(names) else [None]

    @staticmethod
    def _wanted(position: Any, areas: list[str] | None) -> bool:
        """Whether a listed position is worth reading in detail (its title fits a chosen area)."""
        if not areas:
            return True
        found = categorise(
            [clean(as_dict(position).get("name")), clean(as_dict(position).get("department"))]
        )
        return bool(found & set(areas))

    async def collect(self, checkpoint: SourceCheckpoint) -> CollectionResult:
        """List the postings newest first, then read the details of those worth reading."""
        started = asyncio.get_running_loop().time()
        host, domain = self._parts(checkpoint.identifier)
        per_minute = checkpoint.rate_limit_per_minute
        areas = checkpoint.filters.categories if checkpoint.filters else None
        wanted: list[str] = []
        seen: set[str] = set()
        dropped = 0
        declared = 0
        page_limited = False
        for country in self._countries(checkpoint.scope):
            start = 0
            for page in range(self._max_pages + 1):
                if page == self._max_pages:
                    page_limited = True  # more postings are listed than one run reads
                    break
                answer = self._json(
                    await self._get(
                        self._search_url(host, domain, start, country), host, per_minute
                    )
                )
                positions, count = self._listing(answer)
                if start == 0:
                    declared += count
                for position in positions:
                    posting_id = str(as_dict(position).get("id") or "")
                    if not posting_id or posting_id in seen:
                        continue
                    seen.add(posting_id)
                    if self._wanted(position, areas):
                        wanted.append(posting_id)
                    else:
                        dropped += 1
                start += len(positions)
                if len(wanted) > self._max_details:
                    break  # more are known than can be read: the rest need not even be listed
                if not positions or start >= count:
                    break
        truncated = page_limited or len(wanted) > self._max_details
        postings: list[SourcePosting] = []
        for posting_id in wanted[: self._max_details]:
            detail_url = f"https://{host}/api/pcsx/position_details?" + urlencode(
                {"position_id": posting_id, "domain": domain, "hl": "en"}
            )
            try:
                answer = self._json(await self._get(detail_url, host, per_minute))
            except SourceError as error:
                if error.error_class is SourceErrorClass.NOT_FOUND:
                    dropped += 1  # closed between the list and the detail
                    continue
                raise
            detail = as_dict(answer).get("data")
            postings.append(map_posting(detail, host))
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
