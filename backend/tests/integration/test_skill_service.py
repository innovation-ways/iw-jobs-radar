"""Skill canonicalisation and cached pair judgements (T4.3)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import unique
from tests.fake_provider import FakeProvider

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.db.models import Skill, SkillAlias, SkillCandidate, SkillRelation
from jobs_radar.domain.enums import ProviderErrorClass, SkillKind
from jobs_radar.repositories.skills import SkillRepository
from jobs_radar.schemas.extraction import ExtractedSkill
from jobs_radar.services.skills import SkillCanonicaliser, SkillRelationJudge

pytestmark = pytest.mark.integration


def mention(name: str, importance: str = "must") -> ExtractedSkill:
    return ExtractedSkill(name=name, importance=importance, evidence=name)  # type: ignore[arg-type]


async def count(session: AsyncSession, model: type, **filters: object) -> int:
    statement = select(func.count()).select_from(model)
    for column, value in filters.items():
        statement = statement.where(getattr(model, column) == value)
    return int((await session.execute(statement)).scalar_one())


# --- canonicalisation --------------------------------------------------------------------------


async def test_a_mention_of_a_known_skill_maps_to_it_without_creating_anything(
    db_session: AsyncSession,
) -> None:
    name = unique("Python")
    existing = await SkillRepository(db_session).resolve_or_create(name, SkillKind.TECHNOLOGY)
    before = await count(db_session, Skill)
    resolved = await SkillCanonicaliser(db_session).canonicalise([mention(name.upper())])
    assert [(r.skill_id, r.importance) for r in resolved] == [(existing.skill_id, "must")]
    assert await count(db_session, Skill) == before


async def test_an_unknown_mention_creates_a_skill_its_alias_and_an_accepted_candidate(
    db_session: AsyncSession,
) -> None:
    name = unique("Obscure Framework")
    resolved = await SkillCanonicaliser(db_session).canonicalise([mention(name, "nice")])
    skill_id = resolved[0].skill_id
    assert resolved[0].importance == "nice" and resolved[0].name == name
    skill = await db_session.get(Skill, skill_id)
    assert skill is not None and skill.canonical_name == name and skill.kind == "technology"
    assert await count(db_session, SkillAlias, skill_id=skill_id) == 1
    candidate = (
        await db_session.execute(select(SkillCandidate).where(SkillCandidate.skill_id == skill_id))
    ).scalar_one()
    assert (candidate.status, candidate.proposed_canonical_name) == ("accepted", name)


async def test_the_same_mention_twice_creates_one_skill_and_one_candidate(
    db_session: AsyncSession,
) -> None:
    name = unique("Twice")
    canonicaliser = SkillCanonicaliser(db_session)
    first = await canonicaliser.canonicalise([mention(name)])
    second = await canonicaliser.canonicalise([mention(name.lower())])
    assert first[0].skill_id == second[0].skill_id
    assert await count(db_session, SkillCandidate, skill_id=first[0].skill_id) == 1


async def test_duplicates_within_one_job_keep_the_strongest_importance(
    db_session: AsyncSession,
) -> None:
    name = unique("Dup")
    resolved = await SkillCanonicaliser(db_session).canonicalise(
        [mention(name, "nice"), mention(name.upper(), "must")]
    )
    assert len(resolved) == 1 and resolved[0].importance == "must"


# --- pair judgements -----------------------------------------------------------------------------


async def skills(session: AsyncSession, *names: str) -> list[int]:
    repo = SkillRepository(session)
    return [(await repo.resolve_or_create(unique(n), SkillKind.TECHNOLOGY)).skill_id for n in names]


async def test_unmatched_pairs_are_judged_in_one_call_and_cached(db_session: AsyncSession) -> None:
    target, a, b, c = await skills(db_session, "PostgreSQL", "MySQL", "Redis", "Painting")
    names = await SkillRepository(db_session).names({target, a, b, c})
    provider = FakeProvider(
        responder=lambda _r: {
            "equivalent": [],
            "related": [names[a]],
            "unrelated": [names[b], names[c]],
        }
    )
    judge = SkillRelationJudge(db_session, provider)
    relations = await judge.relations(target, [a, b, c])

    assert relations == {a: "related", b: "unrelated", c: "unrelated"}
    assert len(provider.requests) == 1
    assert names[target] in provider.requests[0].user
    for other in (a, b, c):
        low, high = sorted((target, other))
        row = (
            await db_session.execute(
                select(SkillRelation).where(
                    SkillRelation.skill_id_a == low, SkillRelation.skill_id_b == high
                )
            )
        ).scalar_one()
        assert (row.origin, row.provider, row.model, row.prompt_version) == (
            "ai",
            "fixture",
            "fixture-model",
            "skill-relation-v1",
        )

    again = await judge.relations(target, [a, b, c])
    assert again == relations and len(provider.requests) == 1  # cached: no second call


async def test_only_pairs_never_judged_are_sent_to_the_model(db_session: AsyncSession) -> None:
    target, a, d = await skills(db_session, "Kafka", "RabbitMQ", "Pulsar")
    names = await SkillRepository(db_session).names({target, a, d})
    provider = FakeProvider(
        responder=lambda _r: {
            "equivalent": [],
            "related": [],
            "unrelated": list(names.values()),
        }
    )
    judge = SkillRelationJudge(db_session, provider)
    await judge.relations(target, [a])
    await judge.relations(target, [a, d])
    assert len(provider.requests) == 2
    second = provider.requests[1].user
    assert names[d] in second and names[a] not in second  # RabbitMQ was already judged


async def test_the_pair_is_stored_once_whichever_skill_is_the_target(
    db_session: AsyncSession,
) -> None:
    x, y = await skills(db_session, "Alpha", "Beta")
    names = await SkillRepository(db_session).names({x, y})
    provider = FakeProvider(
        responder=lambda _r: {"equivalent": [names[y]], "related": [], "unrelated": []}
    )
    judge = SkillRelationJudge(db_session, provider)
    assert await judge.relations(x, [y]) == {y: "equivalent"}
    assert await judge.relations(y, [x]) == {x: "equivalent"}  # symmetric, from the cache
    assert len(provider.requests) == 1


async def test_names_the_model_invented_are_ignored_and_missing_ones_count_as_unjudged(
    db_session: AsyncSession,
) -> None:
    target, a, b = await skills(db_session, "Terraform", "Ansible", "Chef")
    names = await SkillRepository(db_session).names({a})
    provider = FakeProvider(
        responder=lambda _r: {
            "equivalent": ["Totally Invented"],
            "related": [names[a]],
            "unrelated": [],
        }
    )
    relations = await SkillRelationJudge(db_session, provider).relations(target, [a, b])
    assert relations == {a: "related"}  # b was not answered: unjudged, not guessed
    assert await count(db_session, SkillRelation) >= 1


async def test_a_provider_failure_leaves_pairs_unjudged_and_stores_nothing(
    db_session: AsyncSession,
) -> None:
    target, a = await skills(db_session, "Docker", "Podman")
    provider = FakeProvider([ProviderError(ProviderErrorClass.UNAVAILABLE, "down")])
    relations = await SkillRelationJudge(db_session, provider).relations(target, [a])
    assert relations == {}
    low, high = sorted((target, a))
    assert await count(db_session, SkillRelation, skill_id_a=low, skill_id_b=high) == 0


async def test_a_pair_judged_by_the_user_is_never_overwritten(db_session: AsyncSession) -> None:
    target, a = await skills(db_session, "Vue", "Svelte")
    low, high = sorted((target, a))
    db_session.add(
        SkillRelation(skill_id_a=low, skill_id_b=high, relation="equivalent", origin="user")
    )
    await db_session.flush()
    provider = FakeProvider([])
    relations = await SkillRelationJudge(db_session, provider).relations(target, [a])
    assert relations == {a: "equivalent"} and provider.requests == []


async def test_a_skill_is_not_judged_against_itself(db_session: AsyncSession) -> None:
    (target,) = await skills(db_session, "Solo")
    provider = FakeProvider([])
    assert await SkillRelationJudge(db_session, provider).relations(target, [target]) == {}
    assert provider.requests == []
