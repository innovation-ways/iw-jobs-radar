"""Profile export (no secrets) and confirmed, audited deletion with documents and evidence (T6.6)."""

import json

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.data import sample_profile_input

from jobs_radar.db.models import AuditEvent, Document, Evidence, ProviderConnection

pytestmark = pytest.mark.integration

BASE = "/api/v1"
SECRET = "sk-export-must-never-appear"


async def seed_import(
    session_factory: async_sessionmaker[AsyncSession], profile_id: int
) -> tuple[int, int]:
    """A document, a proposal with an accepted item and its evidence; returns (document, evidence)."""
    from datetime import UTC, datetime

    from jobs_radar.db.models import ProfileProposal, ProposalItem

    async with session_factory() as session:
        document = Document(
            owner_id=1,
            sha256="a" * 64,
            mime_type="text/plain",
            byte_size=10,
            extraction_status="extracted",
        )
        session.add(document)
        await session.flush()
        evidence = Evidence(
            owner_id=1,
            origin="document",
            document_id=document.document_id,
            excerpt="Senior Software Engineer",
            confidence=0.9,
            accepted_at=datetime.now(UTC),
        )
        session.add(evidence)
        proposal = ProfileProposal(
            owner_id=1,
            career_profile_id=profile_id,
            document_id=document.document_id,
            provider_type="ollama",
            provider_model="m",
            prompt_version="profile-import-v1",
        )
        session.add(proposal)
        await session.flush()
        session.add(
            ProposalItem(
                profile_proposal_id=proposal.profile_proposal_id,
                path="headline",
                value_json="x",
                source_excerpt="Senior Software Engineer",
                confidence=0.9,
                review_status="accepted",
                evidence_id=evidence.evidence_id,
            )
        )
        await session.commit()
        return document.document_id, evidence.evidence_id


async def test_the_export_is_portable_and_contains_no_secret(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    profile = (await client.post(f"{BASE}/profiles", json={"title": "Export me"})).json()
    pid = profile["career_profile_id"]
    await client.put(
        f"{BASE}/profiles/{pid}", json={**sample_profile_input(), "expected_current_revision": None}
    )
    await seed_import(session_factory, pid)
    async with session_factory() as session:
        session.add(
            ProviderConnection(
                owner_id=1,
                provider_type="openai",
                display_name="OpenAI",
                endpoint_url="https://api.openai.com/v1",
                model_id="m",
                config_json={},
                credential_ciphertext=SECRET.encode(),
            )
        )
        await session.commit()
    try:
        response = await client.get(f"{BASE}/profiles/{pid}/export")
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
        body = response.json()
        assert body["schema_version"] == 1 and body["profile"]["title"] == "Export me"
        assert body["revisions"][0]["facts"]["headline"] == sample_profile_input()["headline"]
        assert body["documents"][0]["sha256"] == "a" * 64 and "text" not in body["documents"][0]
        assert body["proposals"][0]["items"][0]["review_status"] == "accepted"
        assert (
            SECRET not in response.text
            and "ciphertext" not in response.text
            and "credential" not in response.text.lower()
        )
        assert "api.openai.com" not in response.text  # provider setup is not part of the profile
    finally:
        async with session_factory() as session:
            from sqlalchemy import delete

            await session.execute(delete(ProviderConnection))
            await session.commit()

    async with session_factory() as session:
        event = (
            (
                await session.execute(
                    select(AuditEvent)
                    .where(AuditEvent.action == "career_profile_exported")
                    .order_by(AuditEvent.audit_event_id.desc())
                )
            )
            .scalars()
            .first()
        )
        assert event is not None and event.metadata_json["career_profile_id"] == pid
        assert "Export me" not in json.dumps(event.metadata_json)


async def test_deleting_needs_the_exact_title_and_removes_documents_and_evidence(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    profile = (await client.post(f"{BASE}/profiles", json={"title": "Delete me"})).json()
    pid = profile["career_profile_id"]
    await client.put(
        f"{BASE}/profiles/{pid}", json={**sample_profile_input(), "expected_current_revision": None}
    )
    document_id, evidence_id = await seed_import(session_factory, pid)

    wrong = await client.delete(f"{BASE}/profiles/{pid}", params={"confirm": "delete me"})
    assert (
        wrong.status_code == 422
        and wrong.json()["error"]["details"]["error_class"] == "confirmation_mismatch"
    )
    assert (await client.get(f"{BASE}/profiles/{pid}")).status_code == 200  # nothing was deleted

    done = await client.delete(f"{BASE}/profiles/{pid}", params={"confirm": "Delete me"})
    assert done.status_code == 200
    counts = done.json()["deleted"]
    assert counts["career_profile"] == 1 and counts["document"] == 1 and counts["evidence"] == 1
    assert (await client.get(f"{BASE}/profiles/{pid}")).status_code == 404
    async with session_factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.document_id == document_id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Evidence)
                .where(Evidence.evidence_id == evidence_id)
            )
            == 0
        )
        event = (
            (
                await session.execute(
                    select(AuditEvent)
                    .where(AuditEvent.action == "career_profile_deleted")
                    .order_by(AuditEvent.audit_event_id.desc())
                )
            )
            .scalars()
            .first()
        )
        assert event is not None and "Delete me" not in json.dumps(event.metadata_json)


async def test_unknown_profiles_are_404_for_both(client: httpx.AsyncClient) -> None:
    assert (await client.get(f"{BASE}/profiles/999999/export")).status_code == 404
    assert (
        await client.delete(f"{BASE}/profiles/999999", params={"confirm": "x"})
    ).status_code == 404


async def test_a_document_shared_with_another_profile_is_kept(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    from jobs_radar.db.models import ProfileProposal

    first = (await client.post(f"{BASE}/profiles", json={"title": "First"})).json()[
        "career_profile_id"
    ]
    second = (await client.post(f"{BASE}/profiles", json={"title": "Second"})).json()[
        "career_profile_id"
    ]
    document_id, _ = await seed_import(session_factory, first)
    async with session_factory() as session:
        session.add(
            ProfileProposal(
                owner_id=1,
                career_profile_id=second,
                document_id=document_id,
                provider_type="ollama",
                provider_model="m",
                prompt_version="profile-import-v1",
            )
        )
        await session.commit()
    assert (await client.delete(f"{BASE}/profiles/{first}", params={"confirm": "First"})).json()[
        "deleted"
    ]["document"] == 0
    async with session_factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.document_id == document_id)
            )
            == 1
        )
    await client.delete(f"{BASE}/profiles/{second}", params={"confirm": "Second"})
