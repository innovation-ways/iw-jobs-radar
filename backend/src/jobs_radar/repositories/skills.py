"""Data access for canonical skills and their aliases."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import Skill, SkillAlias
from jobs_radar.domain.enums import SkillKind
from jobs_radar.domain.skills import normalise_skill_name


class SkillRepository:
    """Finds or creates skills by name."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_or_create(self, name: str, kind: SkillKind) -> Skill:
        """Return the skill for ``name`` (matching aliases and names ignoring case and punctuation).

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
            return by_alias
        clean = " ".join(name.split())
        by_name = (
            await self._session.execute(
                select(Skill).where(func.lower(Skill.canonical_name) == clean.lower())
            )
        ).scalar_one_or_none()
        skill = by_name
        if skill is None:
            skill = Skill(canonical_name=clean, kind=kind.value)
            self._session.add(skill)
            await self._session.flush()
        self._session.add(SkillAlias(skill_id=skill.skill_id, alias_normalised=normalised))
        await self._session.flush()
        return skill

    async def names(self, skill_ids: set[int]) -> dict[int, str]:
        """Return the canonical name of each skill id."""
        if not skill_ids:
            return {}
        rows = await self._session.execute(
            select(Skill.skill_id, Skill.canonical_name).where(Skill.skill_id.in_(skill_ids))
        )
        return dict(rows.all())
