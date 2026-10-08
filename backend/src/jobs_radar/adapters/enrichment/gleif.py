"""GLEIF adapter: the legal entity of a company under CC0 (F5).

Only an exact match of the legal name (ignoring case, punctuation and a legal-form suffix such as
Inc. or Ltd) is accepted, and only if exactly one record matches: a registry is searched by name,
so a near match is a different company until the owner says otherwise.
"""

import re
from dataclasses import dataclass

from jobs_radar.adapters.enrichment.base import PublicApi

API = "https://api.gleif.org/api/v1/lei-records"
LICENCE = "CC0-1.0"
_SUFFIX = re.compile(
    r"\b(inc|incorporated|ltd|limited|llc|llp|plc|gmbh|ag|sa|sas|srl|bv|nv|oy|ab|aps|as|co|corp|"
    r"corporation|company|lda|sl|spa)\b\.?",
    re.IGNORECASE,
)
_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalise_legal_name(name: str) -> str:
    """Lower-case a legal name without punctuation and legal-form suffixes."""
    return " ".join(_NON_WORD.sub(" ", _SUFFIX.sub(" ", name.lower())).split())


@dataclass(frozen=True)
class LegalEntity:
    """A legal entity record."""

    lei: str
    legal_name: str
    country: str | None
    status: str | None
    url: str
    licence: str = LICENCE


class GleifAdapter:
    """Finds the legal entity of a company by name."""

    def __init__(self, api: PublicApi) -> None:
        self._api = api

    async def legal_entity(self, name: str) -> LegalEntity | None:
        """Return the one record whose legal name equals ``name``, else ``None``."""
        data = await self._api.get_json(API, {"filter[entity.legalName]": name, "page[size]": "10"})
        wanted = normalise_legal_name(name)
        matches = []
        for record in (data or {}).get("data", []):
            entity = (record.get("attributes") or {}).get("entity") or {}
            legal = (entity.get("legalName") or {}).get("name", "")
            if wanted and normalise_legal_name(legal) == wanted:
                matches.append(
                    LegalEntity(
                        lei=str(record.get("id", "")),
                        legal_name=legal,
                        country=(entity.get("legalAddress") or {}).get("country"),
                        status=entity.get("status"),
                        url=f"https://search.gleif.org/#/record/{record.get('id', '')}",
                    )
                )
        return matches[0] if len(matches) == 1 else None
