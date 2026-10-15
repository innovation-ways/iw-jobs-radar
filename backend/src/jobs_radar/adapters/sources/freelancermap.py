"""freelancermap job board adapter (ADR-075, research R-00176).

freelancermap lists freelance and contract IT projects (many with a stated contract type and a day
or hourly rate in the text). It publishes no API or feed, so this adapter reads the project pages
named in its public sitemap, the same pages any visitor sees. Each page embeds the project as JSON
for its own front end (``ProjectShow``): title, company, contract type, remote share, place, skills
and description. That data is read directly, with no AI and no layout-dependent selectors; a page
that stops carrying it fails the run as ``schema_changed``.

Politeness (the site's terms ask not to overload it): ``robots.txt`` is honoured (a refusal stops
the source), pages are read at the source's rate limit, only entries whose sitemap ``lastmod`` is
within the age window are fetched, newest first, and at most ``MAX_PAGES_PER_RUN`` pages are read;
a run that is cut by the cap is ``truncated`` and never closes postings.
"""

import json
import re
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from jobs_radar.adapters.sources.base import SourceError, SourcePosting
from jobs_radar.adapters.sources.catalogue import require_entry
from jobs_radar.adapters.sources.countries import place_coordinates
from jobs_radar.adapters.sources.html_text import html_to_text
from jobs_radar.adapters.sources.job_board import (
    Candidate,
    JobBoardAdapter,
    MalformedPostingError,
    Page,
    Stream,
)
from jobs_radar.adapters.sources.robots import RobotsGate
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.domain.enums import SourceErrorClass
from jobs_radar.domain.job_board_rules import UNKNOWN, LocationScope, is_recent
from jobs_radar.schemas.source_filters import JobBoardFilters

_ENTRY = require_entry("freelancermap")
MAX_PAGES_PER_RUN = 120
_MAX_SITEMAPS = 3
# Pages tried before concluding that the site's pages no longer carry the project data.
_SCHEMA_PROBE = 3
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>(?:\s*<lastmod>\s*([^<\s]+)\s*</lastmod>)?")
# The site's own wording for the contract types its front end sends.
_CONTRACT_TYPES = {
    "contracting": "Freelance",
    "permanent_position": "Permanent",
    "onsite": "Permanent",
    "employee_leasing": "Agency contract (employee leasing)",
    "leasing": "Agency contract (employee leasing)",
}


def _text(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _time(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def sitemap_entries(xml: str) -> list[tuple[str, str]]:
    """Return ``(address, lastmod)`` of every ``<loc>`` of a sitemap; ``lastmod`` may be empty."""
    return [(match.group(1), match.group(2) or "") for match in _LOC.finditer(xml)]


def project_data(html: str) -> dict[str, Any] | None:
    """Return the ``project`` object embedded in a project page, or ``None`` if there is none."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.select("script.js-react-on-rails-component"):
        if script.get("data-component-name") != "ProjectShow" or not script.string:
            continue
        try:
            data = json.loads(script.string)
        except ValueError:
            return None
        project = data.get("project") if isinstance(data, dict) else None
        return project if isinstance(project, dict) else None
    return None


def parse_project(project: dict[str, Any]) -> Candidate:
    """Convert one embedded project into a candidate; raises :class:`MalformedPostingError`."""
    raw_id, title = project.get("id"), _text(project.get("title"))
    company, url = _text(project.get("company")), project.get("projectUrl")
    if raw_id in (None, "") or not title or not company or not isinstance(url, str) or not url:
        raise MalformedPostingError
    if project.get("isArchived") or project.get("disabled") or project.get("active") is False:
        raise MalformedPostingError
    contract = project.get("contractType")
    contract = contract if isinstance(contract, dict) else {}
    contract_kind = _CONTRACT_TYPES.get(_text(contract.get("contractType")), "")
    remote = contract.get("remoteInPercent")
    remote = remote if isinstance(remote, int | float) and not isinstance(remote, bool) else None
    city = _text(project.get("city"))
    country = project.get("country")
    country_name = _text(country.get("nameEn")) if isinstance(country, dict) else ""
    place = ", ".join(part for part in (city, country_name) if part)
    skills_block = project.get("skills")
    enabled = skills_block.get("enabled") if isinstance(skills_block, dict) else None
    skills = tuple(
        name
        for item in enabled or []
        if isinstance(item, dict) and (name := _text(item.get("nameEn")))
    )
    industry = project.get("industry")
    industry_name = _text(industry.get("nameEn")) if isinstance(industry, dict) else ""
    facts = [
        f"Contract type: {contract_kind}" if contract_kind else "",
        f"Remote: {remote:g}%" if remote is not None else "",
        f"Duration: {project['durationInMonths']} months"
        if isinstance(project.get("durationInMonths"), int)
        else "",
        f"Workload: {project['workload']}%" if isinstance(project.get("workload"), int) else "",
        f"Start: {_text(project.get('startText'))}" if _text(project.get("startText")) else "",
        f"Skills: {', '.join(skills)}" if skills else "",
    ]
    body = project.get("description")
    description = html_to_text(body if isinstance(body, str) else None)
    text = "\n".join(line for line in facts if line)
    posting = SourcePosting(
        external_job_id=str(raw_id),
        title=title,
        source_url=url,
        apply_url=url,
        description_text=f"{text}\n\n{description}".strip(),
        locations=tuple(item for item in (place, "Remote" if remote == 100 else "") if item),
        posted_at=_time(project.get("created")),
        source_updated_at=_time(project.get("updated")),
        departments=(industry_name,) if industry_name else (),
        language=None,
        raw_payload={
            key: project.get(key)
            for key in ("id", "title", "company", "contractType", "city", "created", "updated")
        },
        company_name=company,
    )
    fully_remote = remote == 100
    # Remote eligibility is not published as a list; the text ("Remote in EU") is judged later.
    return Candidate(
        posting,
        UNKNOWN,
        (*skills, industry_name),
        # An unstated share is left to the later judgement (``None``), not treated as on-site.
        remote=None if remote is None else fully_remote,
        place=None if fully_remote or not city else place_coordinates(city),
    )


class FreelancermapAdapter(JobBoardAdapter):
    """Collects the freelancermap project pages named in its sitemap."""

    entry = _ENTRY
    source_type = _ENTRY.source_type

    def __init__(self, client: GuardedHttpClient, **options: Any) -> None:
        super().__init__(client, **options)
        self._robots = RobotsGate(client)

    async def _recent_addresses(
        self, filters: JobBoardFilters, per_minute: int
    ) -> tuple[list[str], bool]:
        """Return the project page addresses to read (newest first) and whether the cap cut them."""
        if not await self._robots.allowed(self.entry.endpoint):
            msg = "The site's robots.txt does not allow automated reading of its project pages."
            raise SourceError(SourceErrorClass.CONFIGURATION, msg)
        key = self.entry.catalogue_key
        index = await self._getter.get(self.entry.endpoint, {}, key, per_minute=per_minute)
        children = [
            address
            for address, _ in sitemap_entries(index.body.decode("utf-8", "replace"))[:_MAX_SITEMAPS]
        ]
        now = self._clock()
        dated: list[tuple[str, str]] = []
        for child in children:
            sitemap = await self._getter.get(child, {}, key, per_minute=per_minute)
            for address, lastmod in sitemap_entries(sitemap.body.decode("utf-8", "replace")):
                # Only project pages of this site are ever requested.
                if "/project/" in address and address.startswith(self.entry.homepage_url):
                    dated.append((address, lastmod))
        # ISO dates sort as text; an entry without a date counts as recent and sorts last.
        fresh = [
            (address, lastmod)
            for address, lastmod in dated
            if is_recent(_time(lastmod), now, filters.max_age_days)
        ]
        fresh.sort(key=lambda item: item[1], reverse=True)
        return [address for address, _ in fresh[:MAX_PAGES_PER_RUN]], len(fresh) > MAX_PAGES_PER_RUN

    def _streams(
        self,
        filters: JobBoardFilters,
        scope: LocationScope,
        *,
        per_minute: int,
        credential: str | None,
    ) -> list[Stream]:
        async def pages() -> AsyncIterator[Page]:
            addresses, capped = await self._recent_addresses(filters, per_minute)
            key = self.entry.catalogue_key
            candidates: list[Candidate] = []
            skipped = parsed = 0
            for index, address in enumerate(addresses, start=1):
                if not await self._robots.allowed(address):
                    skipped += 1
                    continue
                try:
                    response = await self._getter.get(address, {}, key, per_minute=per_minute)
                except SourceError as exc:
                    if exc.error_class is SourceErrorClass.NOT_FOUND:
                        # The page was removed after the sitemap was written: nothing to read.
                        skipped += 1
                        continue
                    if parsed == 0:
                        raise
                    # A page failed after others were read: keep them, and say the run was cut
                    # short so that it never closes postings it did not see.
                    capped = True
                    break
                project = project_data(response.body.decode("utf-8", "replace"))
                if project is None:
                    skipped += 1
                    # Several pages in a row without project data: the layout has changed.
                    if index >= _SCHEMA_PROBE and parsed == 0:
                        msg = "The project pages no longer carry the data the reader expects."
                        raise SourceError(SourceErrorClass.SCHEMA_CHANGED, msg)
                    continue
                parsed += 1
                try:
                    candidates.append(parse_project(project))
                except MalformedPostingError:
                    skipped += 1
            yield Page(candidates, skipped=skipped, capped=capped)

        return [pages]
