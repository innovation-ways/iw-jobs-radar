"""Detects how a company's careers page can be collected (ADR-070.2).

Given the careers address the owner typed, it answers with the boards that can be collected from
it, never writing anything. Order: the address itself (no request), then the page (one request,
``robots.txt`` honoured, redirects only trusted when they stay on the company's domains or reach a
known board), then Eightfold when the page shows its assets, then structured postings on the
company's own site (ADR-070 layer 2). Every candidate is checked with its adapter's ``validate``,
so a proposal is always a real board with postings. No AI is involved.

At most ``MAX_VALIDATIONS`` boards are validated, so a detection stays a handful of requests.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from jobs_radar.adapters.sources.base import JobSourceAdapter, SourceError
from jobs_radar.adapters.sources.robots import RobotsGate
from jobs_radar.core.http import FetchError, GuardedHttpClient
from jobs_radar.domain.careers_markers import (
    AtsMatch,
    ats_in_address,
    ats_in_html,
    looks_script_only,
    mentions_eightfold,
    page_identifier,
)
from jobs_radar.domain.domains import registered_domain
from jobs_radar.domain.enums import SourceErrorClass, SourceType

MAX_VALIDATIONS = 3
_MAX_PAGE_BYTES = 3_000_000
_REFUSED = frozenset({401, 403, 429})
# Errors that say the board may exist but could not be asked right now.
_TRANSIENT = frozenset(
    {
        SourceErrorClass.TIMEOUT,
        SourceErrorClass.NETWORK_ERROR,
        SourceErrorClass.SERVER_ERROR,
        SourceErrorClass.RATE_LIMITED,
    }
)


class DetectionOutcome(StrEnum):
    """What a detection found."""

    DETECTED = "detected"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"
    SCRIPT_ONLY = "script_only"
    BLOCKED = "blocked"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class Candidate:
    """A board the careers page can be collected from, already checked against the real board."""

    source_type: SourceType
    identifier: str
    display_name: str
    postings_count: int
    layer: Literal["ats", "structured_page"]


@dataclass(frozen=True)
class Detection:
    """The result of a detection: an outcome, the candidates, and the reason when there are none."""

    outcome: DetectionOutcome
    candidates: tuple[Candidate, ...]
    reason: str | None = None


class CareersDetector:
    """Finds the collectable boards behind a careers address."""

    def __init__(
        self, client: GuardedHttpClient, adapters: Mapping[SourceType, JobSourceAdapter]
    ) -> None:
        self._client = client
        self._adapters = adapters

    async def detect(self, careers_url: str, *, website_url: str | None = None) -> Detection:
        """Detect the boards behind ``careers_url`` (an already normalised https address)."""
        transient: str | None = None

        direct = ats_in_address(careers_url)
        if direct is not None:
            found, transient = await self._validated([direct])
            if found:
                return Detection(DetectionOutcome.DETECTED, tuple(found))
            return self._nothing(transient, "The board named in this address was not found.")

        robots = RobotsGate(self._client)
        if not await robots.allowed(careers_url):
            reason = "The site's robots.txt does not allow automated reading of this page."
            return Detection(DetectionOutcome.BLOCKED, (), reason)
        try:
            response = await self._client.get(careers_url)
        except FetchError as error:
            if error.error_class == "blocked_url":
                return Detection(DetectionOutcome.BLOCKED, (), "That address cannot be read.")
            return Detection(DetectionOutcome.UNREACHABLE, (), "The careers page did not answer.")
        if response.status in _REFUSED:
            reason = f"The site refused automated access (HTTP {response.status})."
            return Detection(DetectionOutcome.BLOCKED, (), reason)
        if response.status != 200:
            reason = f"The careers page answered with HTTP {response.status}."
            return Detection(DetectionOutcome.UNREACHABLE, (), reason)

        landed = ats_in_address(response.url)
        domains = {registered_domain(careers_url), registered_domain(website_url or "")}
        if landed is None and registered_domain(response.url) not in domains:
            reason = "The careers address leads to another site; its content is not read."
            return Detection(DetectionOutcome.UNSUPPORTED, (), reason)
        if len(response.body) > _MAX_PAGE_BYTES:
            return Detection(DetectionOutcome.UNREACHABLE, (), "The careers page is too large.")

        html = response.body.decode("utf-8", "replace")
        matches = ([landed] if landed else []) + ats_in_html(html)
        unique: list[AtsMatch] = list(dict.fromkeys(matches))
        host = (response.url.split("/")[2] if "//" in response.url else "").lower()
        if not unique and mentions_eightfold(html) and host:
            unique = [AtsMatch(SourceType.EIGHTFOLD, host)]
        found, transient = await self._validated(unique)
        if found:
            outcome = DetectionOutcome.DETECTED if len(found) == 1 else DetectionOutcome.AMBIGUOUS
            return Detection(outcome, tuple(found))
        if unique:
            return self._nothing(transient, "The boards found on the page could not be confirmed.")

        structured = await self._structured(careers_url)
        if structured is not None:
            return Detection(DetectionOutcome.DETECTED, (structured,))
        if looks_script_only(html):
            reason = "The postings are loaded by JavaScript; the page itself holds none."
            return Detection(DetectionOutcome.SCRIPT_ONLY, (), reason)
        return Detection(
            DetectionOutcome.UNSUPPORTED,
            (),
            "No supported applicant system or structured postings were found on this page.",
        )

    @staticmethod
    def _nothing(transient: str | None, reason: str) -> Detection:
        """Return the detection for markers that existed but no board could be confirmed."""
        if transient is not None:
            return Detection(DetectionOutcome.UNREACHABLE, (), transient)
        return Detection(DetectionOutcome.UNSUPPORTED, (), reason)

    async def _validated(self, matches: list[AtsMatch]) -> tuple[list[Candidate], str | None]:
        """Validate up to ``MAX_VALIDATIONS`` boards; also return a transient failure, if any."""
        found: list[Candidate] = []
        transient: str | None = None
        for match in matches[:MAX_VALIDATIONS]:
            adapter = self._adapters.get(match.source_type)
            if adapter is None:
                continue
            try:
                info = await adapter.validate(match.identifier)
            except SourceError as error:
                if error.error_class in _TRANSIENT:
                    transient = error.message
                continue
            found.append(
                Candidate(
                    match.source_type, match.identifier, info.name, info.postings_count, "ats"
                )
            )
        return found, transient

    async def _structured(self, careers_url: str) -> Candidate | None:
        """Layer 2: postings published on the company's own site as schema.org ``JobPosting``."""
        adapter = self._adapters.get(SourceType.PAGE_JSONLD)
        if adapter is None:
            return None
        identifier = page_identifier(careers_url)
        try:
            info = await adapter.validate(identifier)
        except SourceError:
            return None
        return Candidate(
            SourceType.PAGE_JSONLD, identifier, info.name, info.postings_count, "structured_page"
        )
