"""Factories that insert synthetic rows (no real data; ADR-015).

They only ``flush``: tests run inside a transaction that is rolled back, so nothing persists. Names
and identifiers carry a random suffix so tests never collide on unique constraints.
"""

import secrets
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import (
    AuditEvent,
    CareerProfile,
    CollectionRun,
    Company,
    Evidence,
    InboxEvent,
    IntentRevision,
    JobChangeEvent,
    JobExtraction,
    JobInboxItem,
    JobOpportunity,
    JobOpportunityLink,
    JobPosting,
    JobSnapshot,
    MatchEvaluation,
    ProfileRevision,
    ScoreDimension,
    SearchIntent,
    SourceConfiguration,
    SourceRunResult,
)
from jobs_radar.domain.enums import (
    LOCAL_OWNER_ID,
    MATCHING_POLICY_VERSION,
    EvidenceOrigin,
    InboxAction,
    InboxState,
    LinkState,
    ProviderType,
    Recommendation,
    RunStatus,
    RunTrigger,
    ScoreStatus,
    SourceOutcome,
    SourceType,
)
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.job import NormalisedJob
from jobs_radar.schemas.profile import ProfileFacts, ProfilePrivacy
from tests.data import sample_intent, sample_normalised_job, sample_profile_facts

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def unique(prefix: str) -> str:
    """A short unique string such as ``board-3fa9c1d2``."""
    return f"{prefix}-{secrets.token_hex(4)}"


async def make_company(session: AsyncSession, name: str | None = None) -> Company:
    """A synthetic company."""
    name = name or unique("Synthetic Co")
    company = Company(canonical_name=name, name_normalised=name.lower())
    session.add(company)
    await session.flush()
    return company


async def make_source(
    session: AsyncSession,
    company: Company,
    identifier: str | None = None,
    source_type: SourceType = SourceType.GREENHOUSE,
) -> SourceConfiguration:
    """A synthetic board configuration (Greenhouse unless ``source_type`` says otherwise)."""
    identifier = identifier or unique("board")
    source = SourceConfiguration(
        owner_id=LOCAL_OWNER_ID,
        company_id=company.company_id,
        source_type=source_type.value,
        external_identifier=identifier,
        display_name=company.canonical_name,
        url=f"https://boards.example.test/v1/boards/{identifier}/jobs",
        config_json={},
    )
    session.add(source)
    await session.flush()
    return source


async def make_profile(
    session: AsyncSession, title: str | None = None
) -> tuple[CareerProfile, ProfileRevision]:
    """A profile with revision 1 set as current."""
    profile = CareerProfile(owner_id=LOCAL_OWNER_ID, title=title or unique("Profile"))
    session.add(profile)
    await session.flush()
    facts = ProfileFacts.model_validate(sample_profile_facts()).model_dump(mode="json")
    revision = ProfileRevision(
        career_profile_id=profile.career_profile_id,
        revision_number=1,
        facts_json=facts,
        privacy_json=ProfilePrivacy().model_dump(mode="json"),
    )
    session.add(revision)
    await session.flush()
    profile.current_profile_revision_id = revision.profile_revision_id
    await session.flush()
    return profile, revision


async def make_intent(
    session: AsyncSession, profile: CareerProfile
) -> tuple[SearchIntent, IntentRevision]:
    """An intent (the document 13 example) with revision 1 set as current."""
    intent = SearchIntent(
        owner_id=LOCAL_OWNER_ID, career_profile_id=profile.career_profile_id, title=unique("Intent")
    )
    session.add(intent)
    await session.flush()
    definition = IntentDefinition.model_validate(sample_intent()).model_dump(mode="json")
    revision = IntentRevision(
        search_intent_id=intent.search_intent_id, revision_number=1, intent_json=definition
    )
    session.add(revision)
    await session.flush()
    intent.current_intent_revision_id = revision.intent_revision_id
    await session.flush()
    return intent, revision


async def make_posting(
    session: AsyncSession,
    source: SourceConfiguration,
    external_id: str | None = None,
    *,
    title: str | None = None,
    description: str | None = None,
    locations: list[str] | None = None,
    first_seen_at: datetime | None = None,
) -> tuple[JobPosting, JobSnapshot]:
    """A posting with one snapshot; ``title``, ``description`` and ``locations`` override the sample job's."""
    job = NormalisedJob.model_validate(sample_normalised_job()).model_dump(mode="json")
    if title is not None:
        job["title"] = title
    if description is not None:
        job["description_text"] = description
    if locations is not None:
        job["work_arrangement"]["locations"] = [{"raw": raw} for raw in locations]
    content_hash = f"sha256:{secrets.token_hex(32)}"
    posting = JobPosting(
        source_configuration_id=source.source_configuration_id,
        company_id=source.company_id,
        external_job_id=external_id or unique("job"),
        source_type=source.source_type,
        source_url="https://jobs.example.test/1",
        title=job["title"],
        current_content_hash=content_hash,
        first_seen_at=first_seen_at or NOW,
        last_seen_at=first_seen_at or NOW,
    )
    session.add(posting)
    await session.flush()
    snapshot = JobSnapshot(
        job_posting_id=posting.job_posting_id,
        content_hash=content_hash,
        fetched_at=NOW,
        raw_payload_json={"id": posting.external_job_id},
        normalised_json=job,
    )
    session.add(snapshot)
    await session.flush()
    return posting, snapshot


async def make_extraction(
    session: AsyncSession,
    snapshot: JobSnapshot,
    status: str = "succeeded",
    model: str | None = None,
) -> JobExtraction:
    """An extraction of ``snapshot`` with the given status."""
    extraction = JobExtraction(
        job_snapshot_id=snapshot.job_snapshot_id,
        status=status,
        provider=ProviderType.OLLAMA.value,
        model=model or unique("model"),
        prompt_version="extract-v1",
        taxonomy_version_id=1,
        attributes_json={} if status == "succeeded" else None,
        attempts=1,
    )
    session.add(extraction)
    await session.flush()
    return extraction


async def make_opportunity(
    session: AsyncSession, posting: JobPosting, state: LinkState = LinkState.AUTO
) -> JobOpportunity:
    """An opportunity whose primary posting is ``posting``, linked to it."""
    opportunity = JobOpportunity(
        company_id=posting.company_id,
        primary_job_posting_id=posting.job_posting_id,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    session.add(opportunity)
    await session.flush()
    session.add(
        JobOpportunityLink(
            job_opportunity_id=opportunity.job_opportunity_id,
            job_posting_id=posting.job_posting_id,
            state=state.value,
            similarity=Decimal("1.0"),
            features_json={},
            method="dedup-v1",
        )
    )
    await session.flush()
    return opportunity


async def make_inbox_item(session: AsyncSession, opportunity: JobOpportunity) -> JobInboxItem:
    """An unread inbox item for ``opportunity``."""
    item = JobInboxItem(
        owner_id=LOCAL_OWNER_ID,
        job_opportunity_id=opportunity.job_opportunity_id,
        state=InboxState.UNREAD.value,
    )
    session.add(item)
    await session.flush()
    return item


async def make_evaluation(
    session: AsyncSession,
    snapshot: JobSnapshot,
    extraction: JobExtraction,
    profile_revision: ProfileRevision,
    intent_revision: IntentRevision,
) -> tuple[MatchEvaluation, ScoreDimension]:
    """An evaluation with one dimension."""
    evaluation = MatchEvaluation(
        job_snapshot_id=snapshot.job_snapshot_id,
        job_extraction_id=extraction.job_extraction_id,
        profile_revision_id=profile_revision.profile_revision_id,
        intent_revision_id=intent_revision.intent_revision_id,
        policy_version=MATCHING_POLICY_VERSION,
        job_source_hash=snapshot.content_hash,
        fit_score=82,
        recommendation=Recommendation.RECOMMENDED.value,
        gates_json=[],
        weights_json={},
    )
    session.add(evaluation)
    await session.flush()
    dimension = ScoreDimension(
        match_evaluation_id=evaluation.match_evaluation_id,
        dimension_key="skills_technology",
        status=ScoreStatus.MATCH.value,
        quality="strong",
        weight=15,
        effective_weight=Decimal("15"),
        strength=Decimal("0.8"),
        contribution=Decimal("12"),
        evidence_json={},
        explanation="Synthetic explanation.",
    )
    session.add(dimension)
    await session.flush()
    return evaluation, dimension


async def build_full_graph(session: AsyncSession) -> dict[str, Any]:
    """Insert one row into every append-only table and return the useful objects, keyed by name."""
    company = await make_company(session)
    source = await make_source(session, company)
    profile, profile_revision = await make_profile(session)
    intent, intent_revision = await make_intent(session, profile)
    posting, snapshot = await make_posting(session, source)
    extraction = await make_extraction(session, snapshot)
    evaluation, dimension = await make_evaluation(
        session, snapshot, extraction, profile_revision, intent_revision
    )
    opportunity = await make_opportunity(session, posting)
    item = await make_inbox_item(session, opportunity)

    evidence = Evidence(
        owner_id=LOCAL_OWNER_ID, origin=EvidenceOrigin.MANUAL.value, accepted_at=NOW
    )
    event = InboxEvent(
        job_inbox_item_id=item.job_inbox_item_id,
        action=InboxAction.SURFACE_NEW.value,
        actor="system",
        to_state=InboxState.UNREAD.value,
        metadata_json={},
    )
    change = JobChangeEvent(
        job_posting_id=posting.job_posting_id,
        to_job_snapshot_id=snapshot.job_snapshot_id,
        changed_fields=["title"],
        is_material=True,
    )
    run = CollectionRun(
        owner_id=LOCAL_OWNER_ID, trigger=RunTrigger.MANUAL.value, status=RunStatus.SUCCEEDED.value
    )
    session.add_all([evidence, event, change, run])
    await session.flush()
    result = SourceRunResult(
        collection_run_id=run.collection_run_id,
        source_configuration_id=source.source_configuration_id,
        started_at=NOW,
        finished_at=NOW,
        outcome=SourceOutcome.SUCCESS.value,
        duration_ms=10,
    )
    audit = AuditEvent(
        owner_id=LOCAL_OWNER_ID, action="synthetic", subject_type="test", metadata_json={}
    )
    session.add_all([result, audit])
    await session.flush()
    return {
        "company": company,
        "source": source,
        "profile": profile,
        "profile_revision": profile_revision,
        "intent": intent,
        "intent_revision": intent_revision,
        "posting": posting,
        "snapshot": snapshot,
        "extraction": extraction,
        "evaluation": evaluation,
        "dimension": dimension,
        "opportunity": opportunity,
        "item": item,
        "evidence": evidence,
        "event": event,
        "change": change,
        "run": run,
        "result": result,
        "audit": audit,
    }


def session_factory_for(session: AsyncSession, monkeypatch: Any) -> Any:
    """A session factory that always yields ``session`` and never really commits.

    Services that open their own short sessions can then run inside a test's transaction, which is
    rolled back at the end, so nothing persists.
    """
    from contextlib import asynccontextmanager

    monkeypatch.setattr(session, "commit", session.flush)

    @asynccontextmanager
    async def same_session() -> Any:
        yield session

    return same_session
