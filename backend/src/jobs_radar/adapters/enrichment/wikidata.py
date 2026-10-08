"""Wikidata adapter: company facts under CC0 (ADR-025, R-00171 finding F2, F3).

A name search is ambiguous (it also returns libraries with the same name), so only entities that
are companies are returned: an instance-of class from a short list of business classes, or a
description that says so. Industry and headquarters come back as entity references; their labels
are fetched in one more call.
"""

import contextlib
import re
from typing import Any

from jobs_radar.adapters.enrichment.base import EntityCandidate, FactValue, PublicApi

API = "https://www.wikidata.org/w/api.php"
ENTITY_URL = "https://www.wikidata.org/wiki/{}"
LICENCE = "CC0-1.0"
# Instance-of classes that mean "a business": business, company, public company, enterprise,
# multinational corporation, organisation.
_BUSINESS_CLASSES = frozenset({"Q4830453", "Q783794", "Q891723", "Q6881511", "Q161726", "Q43229"})
_BUSINESS_WORDS = re.compile(
    r"\b(company|corporation|startup|start-up|firm|business|consultancy|enterprise|agency|"
    r"manufacturer|provider|multinational)\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"^[+-]?(\d{4})")


def _claim_values(claims: dict[str, Any], prop: str) -> list[Any]:
    values = []
    for claim in claims.get(prop, []):
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if value is not None:
            values.append(value)
    return values


def _first(claims: dict[str, Any], prop: str) -> Any:
    values = _claim_values(claims, prop)
    return values[0] if values else None


class WikidataAdapter:
    """Finds company entities by name."""

    def __init__(self, api: PublicApi) -> None:
        self._api = api

    async def find(self, name: str, *, limit: int = 5) -> list[EntityCandidate]:
        """Return the entities named ``name`` that look like companies."""
        search = await self._api.get_json(
            API,
            {
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "type": "item",
                "limit": str(limit),
                "format": "json",
            },
        )
        ids = [str(hit["id"]) for hit in (search or {}).get("search", []) if "id" in hit]
        if not ids:
            return []
        entities = (
            await self._api.get_json(
                API,
                {
                    "action": "wbgetentities",
                    "ids": "|".join(ids),
                    "props": "claims|labels|descriptions|sitelinks",
                    "languages": "en",
                    "sitefilter": "enwiki",
                    "format": "json",
                },
            )
        ).get("entities", {})
        wanted = [e for e in (entities.get(i) for i in ids) if e and self._is_company(e)]
        references = {
            ref
            for entity in wanted
            for prop in ("P452", "P159")
            for value in [_first(entity.get("claims", {}), prop)]
            if isinstance(value, dict) and (ref := value.get("id"))
        }
        labels = await self._labels(sorted(references))
        return [
            self._candidate(ids[i], entity, labels)
            for i, entity in self._indexed(ids, entities, wanted)
        ]

    @staticmethod
    def _indexed(
        ids: list[str], entities: dict[str, Any], wanted: list[dict[str, Any]]
    ) -> list[tuple[int, dict[str, Any]]]:
        keep = {id(entity) for entity in wanted}
        return [
            (n, entities[i])
            for n, i in enumerate(ids)
            if entities.get(i) and id(entities[i]) in keep
        ]

    @staticmethod
    def _is_company(entity: dict[str, Any]) -> bool:
        classes = {
            value.get("id")
            for value in _claim_values(entity.get("claims", {}), "P31")
            if isinstance(value, dict)
        }
        description = ((entity.get("descriptions") or {}).get("en") or {}).get("value", "")
        return bool(classes & _BUSINESS_CLASSES) or bool(_BUSINESS_WORDS.search(description))

    async def _labels(self, ids: list[str]) -> dict[str, str]:
        if not ids:
            return {}
        answer = await self._api.get_json(
            API,
            {
                "action": "wbgetentities",
                "ids": "|".join(ids),
                "props": "labels",
                "languages": "en",
                "format": "json",
            },
        )
        return {
            qid: ((entity.get("labels") or {}).get("en") or {}).get("value", qid)
            for qid, entity in (answer.get("entities") or {}).items()
        }

    def _candidate(
        self, qid: str, entity: dict[str, Any], labels: dict[str, str]
    ) -> EntityCandidate:
        claims = entity.get("claims", {})
        url = ENTITY_URL.format(qid)

        def fact(value: Any) -> FactValue:
            return FactValue(value, "wikidata", url, LICENCE)

        facts: dict[str, FactValue] = {}
        website = _first(claims, "P856")
        if isinstance(website, str):
            facts["homepage"] = fact(website)
        industry = _first(claims, "P452")
        if isinstance(industry, dict) and industry.get("id"):
            facts["industry"] = fact(labels.get(industry["id"], industry["id"]))
        headquarters = _first(claims, "P159")
        if isinstance(headquarters, dict) and headquarters.get("id"):
            facts["headquarters"] = fact(labels.get(headquarters["id"], headquarters["id"]))
        employees = _first(claims, "P1128")
        if isinstance(employees, dict):
            with contextlib.suppress(KeyError, ValueError):
                facts["employee_count"] = fact(int(float(str(employees["amount"]))))
        inception = _first(claims, "P571")
        if isinstance(inception, dict) and (match := _YEAR.match(str(inception.get("time", "")))):
            facts["founded_year"] = fact(int(match.group(1)))
        github = _first(claims, "P2037")
        label = ((entity.get("labels") or {}).get("en") or {}).get("value", qid)
        return EntityCandidate(
            source_name="wikidata",
            external_id=qid,
            label=label,
            description=((entity.get("descriptions") or {}).get("en") or {}).get("value"),
            website=website if isinstance(website, str) else None,
            facts=facts,
            wikipedia_title=((entity.get("sitelinks") or {}).get("enwiki") or {}).get("title"),
            github_login=github if isinstance(github, str) else None,
        )
