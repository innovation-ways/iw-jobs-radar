"""Merging terms: the old key keeps meaning something, and nothing is deleted (ADR-080, phase 3)."""

from copy import deepcopy

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.data import sample_intent
from tests.evaluation_world import world
from tests.factories import make_profile, unique

from jobs_radar.core.errors import ConflictError, InputValidationError, NotFoundError
from jobs_radar.db.models import TaxonomyTerm
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.repositories.taxonomy import TaxonomyRepository
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.services.evaluation import EvaluationService
from jobs_radar.services.intents import IntentService
from jobs_radar.services.taxonomy import TaxonomyService

pytestmark = pytest.mark.integration


async def two_terms(service: TaxonomyService, kind: str = "role_family") -> tuple[str, str]:
    old = await service.add(kind, unique("Old family"))
    new = await service.add(kind, unique("New family"))
    return old.term_key, new.term_key


async def test_a_merged_term_leaves_the_vocabulary_but_stays_in_the_table(
    db_session: AsyncSession,
) -> None:
    service = TaxonomyService(db_session)
    old, new = await two_terms(service)
    survivor = await service.merge("role_family", old, into=new)
    assert survivor.term_key == new
    repository = TaxonomyRepository(db_session)
    keys = await repository.keys_by_kind(include_inactive=True)
    assert old not in keys["role_family"] and new in keys["role_family"]
    editable = {t.term_key for t in await service.editable_terms()}
    assert new in editable and old not in editable
    stored = await db_session.scalar(select(TaxonomyTerm).where(TaxonomyTerm.term_key == old))
    assert stored is not None and stored.replaced_by_taxonomy_term_id == survivor.taxonomy_term_id
    assert (await repository.replacements())["role_family"][old] == new


async def test_a_merge_is_followed_to_the_end_of_a_chain(db_session: AsyncSession) -> None:
    service = TaxonomyService(db_session)
    a, b = await two_terms(service)
    c = (await service.add("role_family", unique("Third family"))).term_key
    await service.merge("role_family", a, into=b)
    await service.merge("role_family", b, into=c)
    replacements = (await TaxonomyRepository(db_session).replacements())["role_family"]
    assert replacements[a] == c and replacements[b] == c


async def test_a_merge_records_a_taxonomy_version(db_session: AsyncSession) -> None:
    service = TaxonomyService(db_session)
    old, new = await two_terms(service)
    before = await service.current_version_id()
    await service.merge("role_family", old, into=new)
    assert await service.current_version_id() > before


async def test_what_cannot_be_merged(db_session: AsyncSession) -> None:
    service = TaxonomyService(db_session)
    old, new = await two_terms(service)
    sector = (await service.add("sector", unique("Some sector"))).term_key
    with pytest.raises(InputValidationError):  # into itself
        await service.merge("role_family", old, into=old)
    with pytest.raises(NotFoundError):  # a term of another vocabulary is not a target
        await service.merge("role_family", old, into=sector)
    with pytest.raises(InputValidationError):  # not an editable vocabulary
        await service.merge("seniority_level", "junior", into="senior")
    with pytest.raises(NotFoundError):
        await service.merge("role_family", "no_such_term", into=new)
    await service.update("role_family", new, active=False)
    with pytest.raises(ConflictError):  # a switched-off term cannot take over
        await service.merge("role_family", old, into=new)
    await service.update("role_family", new, active=True)
    await service.merge("role_family", old, into=new)
    with pytest.raises(NotFoundError):  # already merged
        await service.merge("role_family", old, into=new)


async def test_an_intent_that_lists_a_merged_term_is_still_valid(db_session: AsyncSession) -> None:
    service = TaxonomyService(db_session)
    old, new = await two_terms(service)
    data = deepcopy(sample_intent())
    data["stances"]["role_families"] += [{"key": old, "stance": "preferred"}]
    profile = (await make_profile(db_session))[0]
    intents = IntentService(db_session)
    created = await intents.create(
        LOCAL_OWNER_ID,
        profile.career_profile_id,
        IntentDefinition.model_validate(data),
        enabled=True,
    )
    await service.merge("role_family", old, into=new)
    data["title"] = "After the merge"
    saved = await intents.save(
        LOCAL_OWNER_ID,
        created.intent.search_intent_id,
        IntentDefinition.model_validate(data),
        expected_current_revision=1,
    )
    assert saved.created is True


async def test_the_preview_tells_which_searches_have_conflicting_stances(
    db_session: AsyncSession,
) -> None:
    service = TaxonomyService(db_session)
    old, new = await two_terms(service)
    profile = (await make_profile(db_session))[0]
    intents = IntentService(db_session)

    async def intent(title: str, entries: list[dict[str, str]]) -> int:
        data = deepcopy(sample_intent())
        data["title"] = title
        data["stances"]["role_families"] += entries
        created = await intents.create(
            LOCAL_OWNER_ID,
            profile.career_profile_id,
            IntentDefinition.model_validate(data),
            enabled=True,
        )
        return int(created.intent.search_intent_id)

    differs = await intent(
        "Differs", [{"key": old, "stance": "preferred"}, {"key": new, "stance": "rejected"}]
    )
    same = await intent(
        "Same", [{"key": old, "stance": "preferred"}, {"key": new, "stance": "preferred"}]
    )
    only_old = await intent("Only old", [{"key": old, "stance": "rejected"}])
    await intent("Neither", [])

    preview = await service.merge_preview(LOCAL_OWNER_ID, "role_family", old, into=new)
    by_id = {item.search_intent_id: item for item in preview}
    assert set(by_id) == {differs, same, only_old}
    assert (by_id[differs].from_stance, by_id[differs].into_stance) == ("preferred", "rejected")
    assert by_id[differs].conflict is True and by_id[same].conflict is False
    assert (by_id[only_old].from_stance, by_id[only_old].into_stance) == ("rejected", None)
    assert by_id[only_old].conflict is False


async def test_scoring_follows_the_merge(db_session: AsyncSession) -> None:
    """A job extracted with the old key matches an intent that only knows the surviving term."""
    service = TaxonomyService(db_session)
    survivor = (await service.add("role_family", unique("Survivor"))).term_key

    async def role_status() -> str:
        """Evaluate a fresh job (extracted as ``ai_solutions_engineering``) for an intent that
        lists only the survivor. An evaluation is stored once per input, hence a fresh world."""
        w = await world(db_session)
        data = deepcopy(sample_intent())
        data["stances"]["role_families"] = [
            {"key": survivor, "stance": "preferred"},
            {"key": "data_analysis", "stance": "rejected"},
        ]
        saved = await IntentService(db_session).save(
            LOCAL_OWNER_ID,
            w.intent_id,
            IntentDefinition.model_validate(data),
            expected_current_revision=1,
        )
        assert saved.view.current is not None
        record = await EvaluationService(db_session, provider=None).evaluate(
            LOCAL_OWNER_ID,
            job_snapshot_id=w.snapshot_id,
            job_extraction_id=w.extraction_id,
            profile_revision_id=w.profile_revision_id,
            intent_revision_id=saved.view.current.intent_revision_id,
            judge=False,
        )
        return next(
            d.status for d in record.dimensions if d.dimension_key == "role_responsibilities"
        )

    assert await role_status() == "mismatch"  # the job's family is not listed in this intent
    await service.merge("role_family", "ai_solutions_engineering", into=survivor)
    assert await role_status() == "match"


async def test_the_api_previews_and_merges(isolated_client: httpx.AsyncClient) -> None:
    async def add(label: str) -> str:
        response = await isolated_client.post(
            "/api/v1/taxonomy/terms", json={"kind": "sector", "label": label}
        )
        assert response.status_code == 201, response.text
        return str(response.json()["term_key"])

    old, new = await add(unique("Old sector")), await add(unique("New sector"))
    base = f"/api/v1/taxonomy/terms/sector/{old}"
    preview = await isolated_client.get(f"{base}/merge-preview", params={"into": new})
    assert preview.status_code == 200 and preview.json() == {"intents": []}

    merged = await isolated_client.post(f"{base}/merge", json={"into": new})
    assert merged.status_code == 200, merged.text
    assert merged.json()["term_key"] == new

    listed = (await isolated_client.get("/api/v1/taxonomy")).json()
    assert {"kind": "sector", "from_key": old, "to_key": new} in listed["replacements"]
    keys = {t["term_key"] for g in listed["groups"] for t in g["terms"]}
    assert old not in keys and new in keys
    assert (await isolated_client.post(f"{base}/merge", json={"into": new})).status_code == 404
    path = f"/api/v1/taxonomy/terms/sector/{new}/merge"
    assert (await isolated_client.post(path, json={"into": new})).status_code == 422
