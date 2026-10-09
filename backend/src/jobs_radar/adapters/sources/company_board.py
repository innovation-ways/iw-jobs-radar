"""Shared behaviour of the company-board adapters: Lever, Ashby and SmartRecruiters (ADR-050).

Like Greenhouse, each of these ATS publishes one board per company through a public,
unauthenticated API. This base class validates the identifier before any request (it becomes part
of a URL), sends conditional requests, spaces and retries requests with :class:`PoliteGetter`, and
guesses a display name from the identifier for the ATS that do not publish one.
"""

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

from jobs_radar.adapters.sources.base import RateLimiter, SourceError
from jobs_radar.adapters.sources.polite_http import PoliteGetter
from jobs_radar.core.http import GuardedHttpClient, HttpResponse
from jobs_radar.domain.enums import SourceErrorClass, SourceType

_TOKEN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def invalid(message: str) -> SourceError:
    """Return the error for an answer that does not have the documented shape."""
    return SourceError(SourceErrorClass.INVALID_PAYLOAD, message)


def as_dict(value: object) -> dict[str, Any]:
    """Return the value if it is an object, otherwise an empty one (missing parts are common)."""
    return value if isinstance(value, dict) else {}


def clean(value: object) -> str:
    """Collapse whitespace of a text field; anything that is not text becomes empty."""
    return " ".join(value.split()) if isinstance(value, str) else ""


def distinct(values: list[str]) -> tuple[str, ...]:
    """Drop blanks and case-insensitive repeats, keeping the first spelling and the order."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value.lower() not in seen:
            seen.add(value.lower())
            result.append(value)
    return tuple(result)


def from_millis(value: object) -> datetime | None:
    """Return the UTC time of a millisecond timestamp, or ``None``."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return datetime.fromtimestamp(value / 1000, UTC)
    return None


def from_iso(value: object) -> datetime | None:
    """Return the UTC time of an ISO 8601 text, or ``None``."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def guess_company_name(identifier: str) -> str:
    """Return a readable company name for an identifier (``synth-co`` becomes ``Synth Co``)."""
    return " ".join(part.capitalize() for part in re.split(r"[-_.]+", identifier) if part)


class CompanyBoardAdapter:
    """Base class: one public board per company on one ATS."""

    source_type: SourceType
    base_url: str

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
            not_found_message="The board was not found. Check the company identifier.",
        )

    def endpoint(self, identifier: str) -> str:
        """Return the board URL stored in the source configuration."""
        return f"{self.base_url}/{self._token(identifier)}"

    @staticmethod
    def _token(identifier: str) -> str:
        if not _TOKEN.match(identifier):
            msg = (
                "A company identifier may only contain letters, digits, dots, hyphens, underscores."
            )
            raise SourceError(SourceErrorClass.CONFIGURATION, msg)
        return identifier

    async def _get(
        self, url: str, key: str, per_minute: int, etag: str | None = None
    ) -> HttpResponse:
        headers = {"If-None-Match": etag} if etag else {}
        return await self._getter.get(url, headers, key, per_minute=per_minute)

    @staticmethod
    def _json(response: HttpResponse) -> Any:
        try:
            return json.loads(response.body)
        except (ValueError, UnicodeDecodeError) as exc:
            msg = "The answer is not valid JSON."
            raise invalid(msg) from exc
