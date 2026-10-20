"""Skills can be tools or equipment and credentials, not only technologies (ADR-080, phase 6a)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import unique

from jobs_radar.domain.enums import SkillKind
from jobs_radar.repositories.skills import SkillRepository

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", list(SkillKind))
async def test_every_skill_kind_can_be_stored(db_session: AsyncSession, kind: SkillKind) -> None:
    skill, created = await SkillRepository(db_session).resolve_mention(unique("Some skill"), kind)
    assert created and skill.kind == kind.value


def test_the_kinds_are_the_three_old_ones_plus_equipment_and_credentials() -> None:
    assert {k.value for k in SkillKind} == {
        "technology",
        "domain_knowledge",
        "method",
        "tool_equipment",
        "credential",
    }
