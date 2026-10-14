"""Pure rules for finding an applicant tracking system from a careers address or page (ADR-070.2).

The owner types a careers address; this module turns it, or the HTML behind it, into the source
type and identifier of a known company board (Greenhouse, Lever, Ashby, SmartRecruiters). It never
fetches anything: the detector adapter does the requests and asks these functions what they mean.
"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from jobs_radar.domain.domains import registered_domain
from jobs_radar.domain.enums import SourceType

_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
# First path segments that belong to an ATS's own machinery, never to a company.
_RESERVED = frozenset(
    {"embed", "api", "v0", "v1", "static", "assets", "jobs", "job_app", "robots.txt", "favicon.ico"}
)
_GREENHOUSE_HOSTS = frozenset(
    {
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
        "boards.eu.greenhouse.io",
        "job-boards.eu.greenhouse.io",
    }
)
_LEVER_HOSTS = frozenset({"jobs.lever.co", "jobs.eu.lever.co"})
_SMARTRECRUITERS_HOSTS = frozenset({"jobs.smartrecruiters.com", "careers.smartrecruiters.com"})
# Anything that looks like an address inside markup or script text, including ``//host/...`` and
# JSON-escaped slashes (handled before matching).
_URL_IN_TEXT = re.compile(r"(?:https?:)?//[A-Za-z0-9.-]+\.[A-Za-z]{2,}/[^\s\"'<>\\)]*")
_EIGHTFOLD = re.compile(r"eightfold\.ai|vscdn\.net", re.IGNORECASE)
_SHELL = re.compile(
    r'id=["\'](?:__nuxt|__next|root|app)["\']|__NEXT_DATA__|data-reactroot|ng-version',
    re.IGNORECASE,
)
_POSTING_LINK = re.compile(
    r'href=["\'][^"\']*/(?:jobs?|vacanc(?:y|ies)|positions?|openings?|postings?|careers?)/[^"\'/?#]+',
    re.IGNORECASE,
)
_NOT_TEXT = re.compile(r"<(script|style|noscript|template|svg)\b.*?</\1>|<[^>]+>", re.S | re.I)
# A page with fewer words than this (and no posting links) holds nothing to read.
_BARE_WORDS = 10


@dataclass(frozen=True)
class AtsMatch:
    """A company board recognised in an address or a page."""

    source_type: SourceType
    identifier: str


def _valid(identifier: str | None) -> str | None:
    if not identifier or identifier.lower() in _RESERVED or not _IDENTIFIER.match(identifier):
        return None
    return identifier


def _segments(path: str) -> list[str]:
    return [part for part in path.split("/") if part]


def ats_in_address(address: str) -> AtsMatch | None:
    """Return the board an address points to, or ``None`` when it is not a known board address.

    Only the address's own host counts: a board address that appears in a query string of another
    site says nothing about that site.
    """
    try:
        parts = urlsplit(address.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    segments = _segments(parts.path)
    first = segments[0] if segments else None
    if host in _GREENHOUSE_HOSTS:
        if first == "embed" and len(segments) >= 2 and segments[1].startswith("job_board"):
            wanted = parse_qs(parts.query).get("for") or []
            return _match(SourceType.GREENHOUSE, wanted[0] if wanted else None)
        return _match(SourceType.GREENHOUSE, first)
    if host == "boards-api.greenhouse.io":
        known = len(segments) >= 3 and segments[0] == "v1" and segments[1] == "boards"
        return _match(SourceType.GREENHOUSE, segments[2] if known else None)
    if host in _LEVER_HOSTS:
        return _match(SourceType.LEVER, first)
    if host == "api.lever.co":
        known = len(segments) >= 3 and segments[0] == "v0" and segments[1] == "postings"
        return _match(SourceType.LEVER, segments[2] if known else None)
    if host == "jobs.ashbyhq.com":
        return _match(SourceType.ASHBY, first)
    if host == "api.ashbyhq.com":
        known = len(segments) >= 3 and segments[0] == "posting-api" and segments[1] == "job-board"
        return _match(SourceType.ASHBY, segments[2] if known else None)
    if host in _SMARTRECRUITERS_HOSTS:
        return _match(SourceType.SMARTRECRUITERS, first)
    if host == "api.smartrecruiters.com":
        known = len(segments) >= 3 and segments[0] == "v1" and segments[1] == "companies"
        return _match(SourceType.SMARTRECRUITERS, segments[2] if known else None)
    return None


def _match(source_type: SourceType, identifier: str | None) -> AtsMatch | None:
    valid = _valid(identifier)
    return AtsMatch(source_type, valid) if valid else None


def ats_in_html(html: str) -> list[AtsMatch]:
    """Return the boards a page links to or embeds, each once, in the order they appear."""
    text = html.replace("\\/", "/")
    found: list[AtsMatch] = []
    for raw in _URL_IN_TEXT.findall(text):
        address = f"https:{raw}" if raw.startswith("//") else raw
        match = ats_in_address(address)
        if match is not None and match not in found:
            found.append(match)
    return found


def mentions_eightfold(html: str) -> bool:
    """Whether a page carries Eightfold's assets (the careers site is then worth probing)."""
    return _EIGHTFOLD.search(html) is not None


def looks_script_only(html: str) -> bool:
    """Whether a page is an application shell whose postings only exist after its scripts run.

    A page with links that look like postings is not. Otherwise it is when it carries a known
    application-shell marker (its menus may be server-rendered, but a listing page with no posting
    link in its HTML is filled in by scripts), or when it is nearly blank.
    """
    if _POSTING_LINK.search(html):
        return False
    if _SHELL.search(html) is not None:
        return True
    return len(_NOT_TEXT.sub(" ", html).split()) < _BARE_WORDS


def normalise_https_address(typed: str) -> str | None:
    """Return a public web address in canonical form, or ``None`` when it is not one.

    The scheme becomes ``https``, the host is lower-cased, the fragment is dropped, and an address
    with credentials, an explicit non-standard port, an IP literal or a bare host is refused. The
    network-level checks (private ranges, redirects) stay in the guarded client.
    """
    text = typed.strip()
    if not text or any(ch.isspace() for ch in text):
        return None
    if "://" not in text:
        if ":" in text.split("/", 1)[0] and not text.split("/", 1)[0].rsplit(":", 1)[1].isdigit():
            return None  # ``javascript:alert(1)`` and similar
        text = f"https://{text}"
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or parts.username or parts.password:
        return None
    if port not in (None, 80, 443) or not parts.hostname or registered_domain(text) is None:
        return None
    query = f"?{parts.query}" if parts.query else ""
    return f"https://{parts.hostname.lower().rstrip('.')}{parts.path or '/'}{query}"


def page_identifier(address: str) -> str:
    """Return the identifier of a careers-page source: host and path, no scheme, query or slash.

    ``https://example.com/careers/?lang=en`` becomes ``example.com/careers``. It is what the
    source stores as its external identifier, so the same page is never added twice.
    """
    parts = urlsplit(address)
    return f"{(parts.hostname or '').lower()}{parts.path.rstrip('/')}"[:200]


def page_address(identifier: str) -> str:
    """Return the address a careers-page identifier stands for (inverse of ``page_identifier``)."""
    return f"https://{identifier}" if "/" in identifier else f"https://{identifier}/"
