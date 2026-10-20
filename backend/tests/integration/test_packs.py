"""Loading domain packs and switching them on (ADR-080, phase 4).

Every test runs in the test's transaction. The packs here are small synthetic ones, so the tests do
not depend on the content of the shipped files (``tests/unit/test_pack_files.py`` covers those).
"""

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import unique

from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import OwnerPack, TaxonomyTerm, TaxonomyTermPack
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.repositories.taxonomy import TaxonomyRepository
from jobs_radar.schemas.pack import PackCredential, PackFile, PackTerm
from jobs_radar.services.packs import PackService
from jobs_radar.services.taxonomy import TaxonomyService

pytestmark = pytest.mark.integration


def pack(
    key: str,
    families: list[tuple[str, str]],
    sectors: list[tuple[str, str]] | None = None,
    version: int = 1,
    credentials: list[PackCredential] | None = None,
) -> PackFile:
    return PackFile(
        schema_version=1,
        key=key,
        version=version,
        name=f"Pack {key}",
        description="A synthetic pack.",
        role_families=[PackTerm(key=k, label=label) for k, label in families],
        sectors=[PackTerm(key=k, label=label) for k, label in (sectors or [])],
        credentials=credentials or [],
    )


async def term(session: AsyncSession, kind: str, key: str) -> TaxonomyTerm | None:
    return await TaxonomyRepository(session).find(kind, key)


async def memberships(session: AsyncSession, pack_key: str) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(TaxonomyTermPack)
                .where(TaxonomyTermPack.pack_key == pack_key)
            )
        ).scalar_one()
    )


async def version(session: AsyncSession) -> int:
    return await TaxonomyRepository(session).current_version_id()


async def test_loading_adds_the_terms_of_a_pack_and_their_membership(
    db_session: AsyncSession,
) -> None:
    key = unique("trades").lower().replace("-", "_").replace(" ", "_")[:40]
    p = pack(
        key,
        [("pk_electrician", "Electrician"), ("pk_plumber", "Plumber")],
        [("pk_building", "Building")],
    )
    before = await version(db_session)
    result = await PackService(db_session, packs=[p]).load()
    assert (result.terms_added, result.memberships_added) == (3, 3)
    electrician = await term(db_session, "role_family", "pk_electrician")
    assert electrician is not None
    assert (electrician.label, electrician.origin, electrician.is_active) == (
        "Electrician",
        "seed",
        True,
    )
    assert await memberships(db_session, key) == 3
    assert await version(db_session) > before


async def test_loading_again_changes_nothing_and_makes_no_version(db_session: AsyncSession) -> None:
    p = pack("idem_pack", [("pk_idem", "Idempotent")])
    service = PackService(db_session, packs=[p])
    await service.load()
    after_first = await version(db_session)
    result = await service.load()
    assert (result.terms_added, result.memberships_added, result.terms_retired) == (0, 0, 0)
    assert await version(db_session) == after_first


async def test_an_owner_edit_is_never_overwritten_by_a_newer_pack(db_session: AsyncSession) -> None:
    await PackService(db_session, packs=[pack("edit_pack", [("pk_edit", "Original label")])]).load()
    await TaxonomyService(db_session).update("role_family", "pk_edit", label="My own label")
    await PackService(
        db_session, packs=[pack("edit_pack", [("pk_edit", "Pack's new label")], version=2)]
    ).load()
    edited = await term(db_session, "role_family", "pk_edit")
    assert edited is not None and edited.label == "My own label"


async def test_a_term_that_already_exists_is_reused_by_another_pack(
    db_session: AsyncSession,
) -> None:
    existing = await term(db_session, "role_family", "security")
    assert existing is not None
    result = await PackService(
        db_session, packs=[pack("shared_pack", [("security", "Security")])]
    ).load()
    assert (result.terms_added, result.memberships_added) == (0, 1)
    again = await term(db_session, "role_family", "security")
    assert again is not None and again.taxonomy_term_id == existing.taxonomy_term_id


async def test_a_term_that_no_pack_lists_any_more_is_switched_off_not_deleted(
    db_session: AsyncSession,
) -> None:
    await PackService(
        db_session, packs=[pack("old_pack", [("pk_gone", "Soon gone"), ("pk_stays", "Stays")])]
    ).load()
    result = await PackService(
        db_session, packs=[pack("old_pack", [("pk_stays", "Stays")], version=2)]
    ).load()
    assert result.terms_retired == 1
    gone = await term(db_session, "role_family", "pk_gone")
    assert gone is not None and gone.is_active is False
    stays = await term(db_session, "role_family", "pk_stays")
    assert stays is not None and stays.is_active is True


async def test_a_term_the_owner_added_is_not_touched_by_the_loader(
    db_session: AsyncSession,
) -> None:
    mine = await TaxonomyService(db_session).add("role_family", unique("My own family"))
    await PackService(db_session, packs=[pack("any_pack", [("pk_any", "Any")])]).load()
    kept = await term(db_session, "role_family", mine.term_key)
    assert kept is not None and kept.is_active is True and kept.origin == "user"


# --- switching packs on ---------------------------------------------------------------------------------


async def test_a_pack_is_offered_only_while_it_is_switched_on(db_session: AsyncSession) -> None:
    service = PackService(db_session, packs=[pack("toggle_pack", [("pk_toggle", "Toggle family")])])
    await service.load()
    repository = TaxonomyRepository(db_session)

    async def offered() -> bool:
        return "pk_toggle" in (await repository.keys_by_kind()).get("role_family", set())

    assert await offered() is False  # loaded, but nobody chose it
    await service.set_active(LOCAL_OWNER_ID, "toggle_pack", active=True)
    assert await offered() is True
    assert "pk_toggle" in (await repository.keys_by_kind(include_inactive=True))["role_family"]
    await service.set_active(LOCAL_OWNER_ID, "toggle_pack", active=False)
    assert await offered() is False
    # Switched off does not mean gone: a saved intent that lists the term still validates.
    assert (
        "pk_toggle"
        in (await repository.keys_by_kind(include_inactive=True, all_packs=True))["role_family"]
    )


async def test_a_term_in_two_packs_is_offered_while_either_is_on(db_session: AsyncSession) -> None:
    service = PackService(
        db_session,
        packs=[
            pack("first_pack", [("pk_both", "In both")]),
            pack("second_pack", [("pk_both", "In both")]),
        ],
    )
    await service.load()
    repository = TaxonomyRepository(db_session)
    await service.set_active(LOCAL_OWNER_ID, "first_pack", active=True)
    await service.set_active(LOCAL_OWNER_ID, "second_pack", active=True)
    await service.set_active(LOCAL_OWNER_ID, "first_pack", active=False)
    assert "pk_both" in (await repository.keys_by_kind())["role_family"]
    await service.set_active(LOCAL_OWNER_ID, "second_pack", active=False)
    assert "pk_both" not in (await repository.keys_by_kind()).get("role_family", set())


async def test_terms_in_no_pack_are_always_offered(db_session: AsyncSession) -> None:
    await db_session.execute(delete(OwnerPack))  # an installation with nothing switched on
    mine = await TaxonomyService(db_session).add("role_family", unique("Mine"))
    offered = await TaxonomyRepository(db_session).keys_by_kind()
    assert "other" in offered["role_family"] and mine.term_key in offered["role_family"]
    assert "security" not in offered["role_family"]  # software vocabulary needs its pack
    assert "senior" in offered["seniority_level"]  # the global kinds do not depend on packs


async def test_switching_a_pack_on_twice_is_harmless_and_records_one_version(
    db_session: AsyncSession,
) -> None:
    service = PackService(db_session, packs=[pack("twice_pack", [("pk_twice", "Twice")])])
    await service.load()
    await service.set_active(LOCAL_OWNER_ID, "twice_pack", active=True)
    after = await version(db_session)
    await service.set_active(LOCAL_OWNER_ID, "twice_pack", active=True)
    assert await version(db_session) == after
    rows = (
        await db_session.execute(
            select(func.count()).select_from(OwnerPack).where(OwnerPack.pack_key == "twice_pack")
        )
    ).scalar_one()
    assert rows == 1


async def test_an_unknown_pack_cannot_be_switched_on(db_session: AsyncSession) -> None:
    with pytest.raises(NotFoundError):
        await PackService(db_session, packs=[]).set_active(
            LOCAL_OWNER_ID, "no_such_pack", active=True
        )


async def test_the_list_tells_what_each_pack_holds_and_whether_it_is_on(
    db_session: AsyncSession,
) -> None:
    service = PackService(
        db_session, packs=[pack("list_pack", [("pk_l1", "L1"), ("pk_l2", "L2")], [("pk_ls", "LS")])]
    )
    await service.load()
    await service.set_active(LOCAL_OWNER_ID, "list_pack", active=True)
    (info,) = await service.available(LOCAL_OWNER_ID)
    assert (info.key, info.name, info.active) == ("list_pack", "Pack list_pack", True)
    assert (info.role_family_count, info.sector_count) == (2, 1)


# --- the shipped packs -------------------------------------------------------------------------------------


async def test_loading_the_shipped_packs_leaves_the_owners_vocabulary_exactly_as_it_is(
    db_session: AsyncSession,
) -> None:
    """With the software pack on (as for the owner), nothing is added, lost or relabelled."""
    from tests.golden import golden_taxonomy

    repository = TaxonomyRepository(db_session)
    before = await repository.keys_by_kind()
    result = await PackService(db_session).load()
    assert result.terms_retired == 0 and result.terms_added > 100
    after = await repository.keys_by_kind()
    for kind in ("role_family", "sector"):
        assert after[kind] == before[kind] == set(golden_taxonomy()[kind])


async def test_every_shipped_pack_can_be_switched_on_and_offers_its_terms(
    db_session: AsyncSession,
) -> None:
    from jobs_radar.services.packs import shipped_packs

    service = PackService(db_session)
    await service.load()
    repository = TaxonomyRepository(db_session)
    for pack in shipped_packs():
        await service.set_active(LOCAL_OWNER_ID, pack.key, active=True)
    offered = await repository.keys_by_kind()
    for pack in shipped_packs():
        assert {t.key for t in pack.role_families} <= offered["role_family"], pack.key
        assert {t.key for t in pack.sectors} <= offered["sector"], pack.key


async def test_loading_the_shipped_packs_twice_changes_nothing(db_session: AsyncSession) -> None:
    service = PackService(db_session)
    await service.load()
    second = await service.load()
    assert (second.terms_added, second.memberships_added, second.terms_retired) == (0, 0, 0)


# --- credentials (ADR-080, phase 6a) ------------------------------------------------------------------


async def skill_named(session: AsyncSession, name: str):  # type: ignore[no-untyped-def]
    from sqlalchemy import func as sql_func

    from jobs_radar.db.models import Skill

    return await session.scalar(
        select(Skill).where(sql_func.lower(Skill.canonical_name) == name.lower())
    )


async def aliases_of(session: AsyncSession, skill_id: int) -> set[str]:
    from jobs_radar.db.models import SkillAlias

    rows = await session.execute(
        select(SkillAlias.alias_normalised).where(SkillAlias.skill_id == skill_id)
    )
    return set(rows.scalars())


async def test_a_pack_creates_its_credentials_as_skills_with_their_aliases(
    db_session: AsyncSession,
) -> None:
    name = unique("Gas Safe registration")
    p = pack(
        "cred_pack",
        [("pk_cred", "Credential family")],
        credentials=[PackCredential(name=name, aliases=["gas safe", "gas safe card"])],
    )
    result = await PackService(db_session, packs=[p]).load()
    assert result.credentials_added == 1
    skill = await skill_named(db_session, name)
    assert skill is not None and skill.kind == "credential"
    aliases = await aliases_of(db_session, skill.skill_id)
    assert {"gas safe", "gas safe card"} <= aliases


async def test_loading_credentials_again_adds_nothing(db_session: AsyncSession) -> None:
    p = pack(
        "cred_again",
        [("pk_again", "Again")],
        credentials=[PackCredential(name=unique("Forklift licence"), aliases=["forklift ticket"])],
    )
    service = PackService(db_session, packs=[p])
    await service.load()
    second = await service.load()
    assert second.credentials_added == 0


async def test_a_skill_that_exists_is_kept_as_it_is_and_gains_the_aliases(
    db_session: AsyncSession,
) -> None:
    """A name the owner already has (for example from a CV) is not duplicated or retyped."""
    from jobs_radar.domain.enums import SkillKind
    from jobs_radar.repositories.skills import SkillRepository

    name = unique("First aid certificate")
    existing, _ = await SkillRepository(db_session).resolve_mention(name, SkillKind.METHOD)
    p = pack(
        "cred_existing",
        [("pk_existing", "Existing")],
        credentials=[PackCredential(name=name, aliases=["first aid ticket"])],
    )
    result = await PackService(db_session, packs=[p]).load()
    assert result.credentials_added == 0
    again = await skill_named(db_session, name)
    assert again is not None and again.skill_id == existing.skill_id and again.kind == "method"
    assert "first aid ticket" in await aliases_of(db_session, existing.skill_id)


async def test_an_alias_that_belongs_to_another_skill_is_not_taken_over(
    db_session: AsyncSession,
) -> None:
    from jobs_radar.domain.enums import SkillKind
    from jobs_radar.repositories.skills import SkillRepository

    other, _ = await SkillRepository(db_session).resolve_mention(
        unique("Other skill"), SkillKind.TECHNOLOGY
    )
    shared = sorted(await aliases_of(db_session, other.skill_id))[0]
    name = unique("Brand new credential")
    p = pack(
        "cred_alias",
        [("pk_alias", "Alias")],
        credentials=[PackCredential(name=name, aliases=[shared])],
    )
    await PackService(db_session, packs=[p]).load()
    new = await skill_named(db_session, name)
    assert new is not None
    assert shared not in await aliases_of(db_session, new.skill_id)
    assert shared in await aliases_of(db_session, other.skill_id)
