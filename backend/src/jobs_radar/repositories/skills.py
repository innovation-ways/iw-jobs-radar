"""Data access for canonical skills and their aliases."""

from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import Skill, SkillAlias, SkillCandidate, SkillRelation
from jobs_radar.domain.enums import JudgementOrigin, SkillKind, SkillRelationKind
from jobs_radar.domain.skills import normalise_skill_name


class SkillRepository:
    """Finds or creates skills by name."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_mention(self, name: str, kind: SkillKind) -> tuple[Skill, bool]:
        """Return ``(skill, created)`` for ``name``, matching aliases and names ignoring case.

        A name that matches nothing creates a new skill of ``kind`` plus its alias.
        """
        normalised = normalise_skill_name(name)
        by_alias = (
            await self._session.execute(
                select(Skill)
                .join(SkillAlias, SkillAlias.skill_id == Skill.skill_id)
                .where(SkillAlias.alias_normalised == normalised)
            )
        ).scalar_one_or_none()
        if by_alias is not None:
            return by_alias, False
        clean = " ".join(name.split())
        skill = (
            await self._session.execute(
                select(Skill).where(func.lower(Skill.canonical_name) == clean.lower())
            )
        ).scalar_one_or_none()
        created = skill is None
        if skill is None:
            skill = Skill(canonical_name=clean, kind=kind.value)
            self._session.add(skill)
            await self._session.flush()
        self._session.add(SkillAlias(skill_id=skill.skill_id, alias_normalised=normalised))
        await self._session.flush()
        return skill, created

    async def resolve_or_create(self, name: str, kind: SkillKind) -> Skill:
        """Return the skill for ``name``, creating it when it is new."""
        return (await self.resolve_mention(name, kind))[0]

    async def record_accepted_candidate(self, skill: Skill, mention: str) -> SkillCandidate:
        """Record that a mention created ``skill`` automatically (audit of auto-accepted skills)."""
        candidate = SkillCandidate(
            proposed_canonical_name=skill.canonical_name,
            alias_normalised=normalise_skill_name(mention),
            status="accepted",
            skill_id=skill.skill_id,
        )
        self._session.add(candidate)
        await self._session.flush()
        return candidate

    async def cached_relations(self, target: int, others: Sequence[int]) -> dict[int, str]:
        """Return the stored relation of ``target`` with each of ``others`` that has one."""
        if not others:
            return {}
        rows = await self._session.execute(
            select(SkillRelation).where(
                or_(
                    (SkillRelation.skill_id_a == target) & SkillRelation.skill_id_b.in_(others),
                    (SkillRelation.skill_id_b == target) & SkillRelation.skill_id_a.in_(others),
                )
            )
        )
        return {
            row.skill_id_b if row.skill_id_a == target else row.skill_id_a: row.relation
            for row in rows.scalars()
        }

    async def add_relation(
        self,
        first: int,
        second: int,
        relation: SkillRelationKind,
        *,
        origin: JudgementOrigin,
        provider: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        """Store a pair judgement once (``skill_id_a < skill_id_b``); an existing one is kept."""
        low, high = sorted((first, second))
        statement = (
            pg_insert(SkillRelation)
            .values(
                skill_id_a=low,
                skill_id_b=high,
                relation=relation.value,
                origin=origin.value,
                provider=provider,
                model=model,
                prompt_version=prompt_version,
            )
            .on_conflict_do_nothing(constraint="uq_skill_relation_skill_id_a_skill_id_b")
        )
        await self._session.execute(statement)

    async def names(self, skill_ids: set[int]) -> dict[int, str]:
        """Return the canonical name of each skill id."""
        if not skill_ids:
            return {}
        rows = await self._session.execute(
            select(Skill.skill_id, Skill.canonical_name).where(Skill.skill_id.in_(skill_ids))
        )
        return dict(rows.all())
