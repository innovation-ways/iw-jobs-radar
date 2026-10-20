"""Skill canonicalisation and cached skill-pair judgements (document 13, sections 2.2 and 6.1).

* **Canonicalisation:** a skill mention from a job maps to a canonical skill through aliases; a
  mention that matches nothing creates the skill at once and records an *accepted* candidate, so
  the pair judgement below always has a skill to compare (ADR-044).
* **Pair judgement:** the only profile-dependent AI step. For one job skill and the profile's
  skills it asks the model, in one call, how each unmatched pair relates (``equivalent``,
  ``related`` or ``unrelated``) and caches every answer once per pair, so a pair is never judged
  twice and re-scoring after a weight change makes no AI call. Pairs the model did not answer, or
  a failing provider, leave pairs *unjudged* (never guessed).
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.providers.base import ExtractionProvider, ExtractionRequest, ProviderError
from jobs_radar.domain.enums import JudgementOrigin, SkillKind, SkillRelationKind
from jobs_radar.domain.skills import normalise_skill_name
from jobs_radar.repositories.skills import SkillRepository
from jobs_radar.schemas.extraction import ExtractedSkill

SKILL_RELATION_PROMPT_VERSION = "skill-relation-v1"

_SYSTEM = "\n".join(
    [
        "You judge how skills relate for hiring and answer with a JSON object.",
        "equivalent: one could replace the other in a job requirement (for example PostgreSQL and "
        "Postgres).",
        "related: the same family or a transferable skill (for example PostgreSQL and MySQL).",
        "unrelated: anything else.",
        "Put every candidate in exactly one of the three lists, using its name exactly as given. "
        "Answer with the JSON object only.",
    ]
)
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        kind: {"type": "array", "items": {"type": "string"}}
        for kind in ("equivalent", "related", "unrelated")
    },
    "required": ["equivalent", "related", "unrelated"],
}
_ORDER = ("equivalent", "related", "unrelated")  # precedence if a name appears in several lists


@dataclass(frozen=True)
class ResolvedSkill:
    """A job's skill mention resolved to a canonical skill."""

    skill_id: int
    name: str
    importance: str


class SkillCanonicaliser:
    """Maps skill mentions of a job to canonical skills."""

    def __init__(self, session: AsyncSession) -> None:
        self._skills = SkillRepository(session)

    async def canonicalise(
        self, mentions: Sequence[ExtractedSkill], kind: SkillKind = SkillKind.TECHNOLOGY
    ) -> list[ResolvedSkill]:
        """Resolve each mention, creating skills of ``kind`` for unknown ones.

        A mention that matches an existing skill keeps that skill's own kind. Duplicates keep
        ``must``.
        """
        resolved: dict[int, ResolvedSkill] = {}
        for mention in mentions:
            skill, created = await self._skills.resolve_mention(mention.name, kind)
            if created:
                await self._skills.record_accepted_candidate(skill, mention.name)
            current = resolved.get(skill.skill_id)
            if current is None or (current.importance == "nice" and mention.importance == "must"):
                resolved[skill.skill_id] = ResolvedSkill(
                    skill.skill_id, skill.canonical_name, mention.importance
                )
        return list(resolved.values())


class SkillRelationJudge:
    """Judges and caches how one skill relates to others."""

    def __init__(self, session: AsyncSession, provider: ExtractionProvider) -> None:
        self._skills = SkillRepository(session)
        self._provider = provider

    async def relations(self, target: int, others: Sequence[int]) -> dict[int, str]:
        """Return the relation of ``target`` with each of ``others`` that is known or judgeable.

        Cached pairs (including those judged by the user) are used as they are; the rest are sent
        to the model in one call. Pairs that remain unjudged are absent from the result.
        """
        wanted = [skill_id for skill_id in dict.fromkeys(others) if skill_id != target]
        known = await self._skills.cached_relations(target, wanted)
        missing = [skill_id for skill_id in wanted if skill_id not in known]
        if missing:
            known.update(await self._judge(target, missing))
        return known

    async def _judge(self, target: int, missing: list[int]) -> dict[int, str]:
        names = await self._skills.names({target, *missing})
        missing = [skill_id for skill_id in missing if skill_id in names]  # skip dangling ids
        if target not in names or not missing:
            return {}
        by_normalised = {normalise_skill_name(names[skill_id]): skill_id for skill_id in missing}
        request = ExtractionRequest(
            system=_SYSTEM,
            user=f"Skill: {names[target]}\nCandidates:\n"
            + "\n".join(f"- {names[skill_id]}" for skill_id in missing),
            json_schema=_SCHEMA,
        )
        try:
            answer = await self._provider.extract(request)
            judged = self._parse(answer.content, by_normalised)
        # A failing provider or an unusable answer leaves the pairs unjudged: never guessed.
        except (ProviderError, ValueError):
            return {}
        for skill_id, relation in judged.items():
            await self._skills.add_relation(
                target,
                skill_id,
                SkillRelationKind(relation),
                origin=JudgementOrigin.AI,
                provider=self._provider.provider,
                model=self._provider.model,
                prompt_version=SKILL_RELATION_PROMPT_VERSION,
            )
        return judged

    @staticmethod
    def _parse(content: str, by_normalised: dict[str, int]) -> dict[int, str]:
        data = json.loads(content)
        if not isinstance(data, dict):
            msg = "not an object"
            raise ValueError(msg)
        judged: dict[int, str] = {}
        for relation in _ORDER:
            for name in data.get(relation) or []:
                skill_id = by_normalised.get(normalise_skill_name(str(name)))
                if skill_id is not None and skill_id not in judged:
                    judged[skill_id] = relation  # names the model invented are simply ignored
        return judged
