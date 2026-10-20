"""The owner edits role families and sectors; nothing is ever deleted (ADR-080, phase 3).

Every test runs inside the test's transaction (``commit`` is a flush), so the shared test database
keeps exactly the vocabulary the characterisation tests record.
"""

from collections.abc import AsyncIterator
from copy import deepcopy

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.data import sample_intent
from tests.factories import make_profile, unique

from jobs_radar.api.deps import get_session
from jobs_radar.core.errors import ConflictError, InputValidationError, NotFoundError
from jobs_radar.db.models import TaxonomyTerm, TaxonomyVersion
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.repositories.taxonomy import TaxonomyRepository
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.services.intents import IntentService
from jobs_radar.services.taxonomy import TaxonomyService

pytestmark = pytest.mark.integration


async def current_version(session: AsyncSession) -> int:
    return int(
        (await session.execute(select(func.max(TaxonomyVersion.taxonomy_version_id)))).scalar_one()
    )


async def test_adding_a_term_gives_it_a_key_a_user_origin_and_a_new_version(
    db_session: AsyncSession,
) -> None:
    before = await current_version(db_session)
    label = unique("Electrician")
    term = await TaxonomyService(db_session).add("role_family", label)
    assert term.label == label and term.origin == "user" and term.is_active is True
    assert term.term_key.startswith("electrician")
    # Identity values are not reused after a rollback, so only the order is certain.
    assert term.introduced_in_taxonomy_version_id == await current_version(db_session) > before
    keys = await TaxonomyRepository(db_session).keys_by_kind()
    assert term.term_key in keys["role_family"]


async def test_a_kind_that_is_not_editable_is_refused(db_session: AsyncSession) -> None:
    with pytest.raises(InputValidationError):
        await TaxonomyService(db_session).add("seniority_level", "Wizard")


async def test_a_label_that_gives_no_key_is_refused(db_session: AsyncSession) -> None:
    with pytest.raises(InputValidationError):
        await TaxonomyService(db_session).add("sector", "&&&")


async def test_a_repeated_label_conflicts_whatever_the_case(db_session: AsyncSession) -> None:
    service = TaxonomyService(db_session)
    label = unique("Plumbing")
    await service.add("sector", label)
    with pytest.raises(ConflictError):
        await service.add("sector", label.upper())
    # An existing seed label conflicts too.
    with pytest.raises(ConflictError):
        await service.add("role_family", "Security")


async def test_the_same_label_may_exist_in_another_kind(db_session: AsyncSession) -> None:
    service = TaxonomyService(db_session)
    label = unique("Logistics")
    await service.add("sector", label)
    assert (await service.add("role_family", label)).kind == "role_family"


async def test_renaming_keeps_the_key_and_bumps_the_version_once(db_session: AsyncSession) -> None:
    service = TaxonomyService(db_session)
    term = await service.add("role_family", unique("Wiring"))
    original_label = term.label  # the session returns the same object, which the update changes
    before = await current_version(db_session)
    renamed = await service.update("role_family", term.term_key, label=unique("Electrical wiring"))
    assert renamed.term_key == term.term_key and renamed.label != original_label
    assert await current_version(db_session) > before
    bumped = await current_version(db_session)
    # Saying the same thing again changes nothing and creates no version (ADR-043 style).
    again = await service.update("role_family", term.term_key, label=renamed.label)
    assert again.label == renamed.label and await current_version(db_session) == bumped


async def test_a_seed_term_can_be_relabelled_but_keeps_its_key(db_session: AsyncSession) -> None:
    service = TaxonomyService(db_session)
    changed = await service.update("role_family", "security", label="Information security")
    assert changed.term_key == "security" and changed.origin == "seed"


async def test_a_deactivated_term_leaves_the_choices_and_the_prompt_but_not_the_data(
    db_session: AsyncSession,
) -> None:
    service = TaxonomyService(db_session)
    repository = TaxonomyRepository(db_session)
    term = await service.add("role_family", unique("Welding"))
    await service.update("role_family", term.term_key, active=False)

    offered = {t.term_key for g in (await service.groups()).values() for t in g}
    everything = {
        t.term_key for g in (await service.groups(include_inactive=True)).values() for t in g
    }
    assert term.term_key not in offered and term.term_key in everything
    # The extraction asks the model with active terms only.
    assert term.term_key not in (await repository.keys_by_kind())["role_family"]
    # The row is still there, with its history.
    stored = await db_session.scalar(
        select(TaxonomyTerm).where(TaxonomyTerm.term_key == term.term_key)
    )
    assert stored is not None and stored.is_active is False

    await service.update("role_family", term.term_key, active=True)
    assert term.term_key in (await repository.keys_by_kind())["role_family"]


async def test_an_intent_that_lists_a_deactivated_term_is_still_valid(
    db_session: AsyncSession,
) -> None:
    """Stored stances keep working; the owner can save the intent again (ADR-080, point 4)."""
    service = TaxonomyService(db_session)
    term = await service.add("role_family", unique("Carpentry"))
    data = deepcopy(sample_intent())
    data["stances"]["role_families"].append({"key": term.term_key, "stance": "preferred"})
    profile = (await make_profile(db_session))[0]
    intents = IntentService(db_session)
    created = await intents.create(
        LOCAL_OWNER_ID,
        profile.career_profile_id,
        IntentDefinition.model_validate(data),
        enabled=True,
    )
    await service.update("role_family", term.term_key, active=False)
    data["title"] = "Renamed search"
    saved = await intents.save(
        LOCAL_OWNER_ID,
        created.intent.search_intent_id,
        IntentDefinition.model_validate(data),
        expected_current_revision=1,
    )
    assert saved.created is True


async def test_an_unknown_term_is_not_found(db_session: AsyncSession) -> None:
    with pytest.raises(NotFoundError):
        await TaxonomyService(db_session).update("role_family", "no_such_term", active=False)


async def test_the_other_vocabularies_cannot_be_changed(db_session: AsyncSession) -> None:
    with pytest.raises(InputValidationError):
        await TaxonomyService(db_session).update("seniority_level", "senior", active=False)


# --- the HTTP interface -----------------------------------------------------------------------------


@pytest_asyncio.fixture
async def isolated_client(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    """The shared client with every request running in the test's transaction."""
    monkeypatch.setattr(db_session, "commit", db_session.flush)

    async def same_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setitem(app.dependency_overrides, get_session, same_session)
    yield client


async def test_the_api_adds_renames_and_deactivates_a_term(
    isolated_client: httpx.AsyncClient,
) -> None:
    label = unique("Heat pumps")
    created = await isolated_client.post(
        "/api/v1/taxonomy/terms", json={"kind": "role_family", "label": label}
    )
    assert created.status_code == 201, created.text
    term = created.json()
    assert term["label"] == label and term["origin"] == "user" and term["active"] is True

    listed = (await isolated_client.get("/api/v1/taxonomy/terms")).json()
    assert {(t["kind"], t["term_key"]) for t in listed["terms"]} >= {
        ("role_family", term["term_key"])
    }
    assert {t["kind"] for t in listed["terms"]} == {"role_family", "sector"}

    path = f"/api/v1/taxonomy/terms/role_family/{term['term_key']}"
    renamed = await isolated_client.patch(path, json={"label": unique("Heat pump install")})
    assert renamed.status_code == 200 and renamed.json()["term_key"] == term["term_key"]

    off = await isolated_client.patch(path, json={"active": False})
    assert off.status_code == 200 and off.json()["active"] is False
    offered = (await isolated_client.get("/api/v1/taxonomy")).json()
    keys = {t["term_key"] for g in offered["groups"] for t in g["terms"]}
    assert term["term_key"] not in keys


async def test_the_api_reports_conflicts_and_bad_input(isolated_client: httpx.AsyncClient) -> None:
    body = {"kind": "sector", "label": unique("Shipbuilding")}
    assert (await isolated_client.post("/api/v1/taxonomy/terms", json=body)).status_code == 201
    assert (await isolated_client.post("/api/v1/taxonomy/terms", json=body)).status_code == 409
    bad_kind = await isolated_client.post(
        "/api/v1/taxonomy/terms", json={"kind": "benefit", "label": "Free lunch"}
    )
    assert bad_kind.status_code == 422
    assert (
        await isolated_client.patch("/api/v1/taxonomy/terms/sector/nope", json={"active": False})
    ).status_code == 404
    assert (
        await isolated_client.patch("/api/v1/taxonomy/terms/sector/energy_utilities", json={})
    ).status_code == 422


async def test_terms_cannot_be_deleted_through_the_api(isolated_client: httpx.AsyncClient) -> None:
    response = await isolated_client.delete("/api/v1/taxonomy/terms/sector/energy_utilities")
    assert response.status_code == 405
