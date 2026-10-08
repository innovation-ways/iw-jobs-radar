"""Audited deletion of personal data (UC-08, ADR-030).

This is the only code path allowed to bypass the append-only triggers. It enables the bypass for
the shortest possible span, always switches it off again, and writes an audit event that contains
identifiers and counts but never the deleted content (TR-8.4).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import Select, delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import (
    AuditEvent,
    CareerProfile,
    Document,
    Evidence,
    IntentRevision,
    MatchEvaluation,
    ProfileProposal,
    ProfileRevision,
    ProposalItem,
    SearchIntent,
    TrendWeekly,
)


@asynccontextmanager
async def allow_mutation(session: AsyncSession) -> AsyncIterator[None]:
    """Temporarily let the current transaction modify append-only tables."""
    await session.execute(text("SELECT set_config('jobs_radar.allow_mutation', 'on', true)"))
    try:
        yield
    finally:
        # Explicitly switched off: SET LOCAL alone would stay active until the transaction ends.
        await session.execute(text("SELECT set_config('jobs_radar.allow_mutation', 'off', true)"))


async def delete_career_profile(
    session: AsyncSession, *, owner_id: int, career_profile_id: int
) -> dict[str, int]:
    """Delete a profile and everything hanging off it, record an audit event, return the counts.

    Removes the profile's revisions, its intents and their revisions, the evaluations that used
    those revisions, its proposals, the evidence of their items, the metadata of documents that no
    other profile's proposal uses, and its trend aggregates. Inbox decisions belong to job
    opportunities, not to the profile, and stay. The caller owns the transaction.

    Raises:
        NotFoundError: if the profile does not exist or belongs to another owner.
    """
    profile = (
        await session.execute(
            select(CareerProfile).where(
                CareerProfile.career_profile_id == career_profile_id,
                CareerProfile.owner_id == owner_id,
            )
        )
    ).scalar_one_or_none()
    if profile is None:
        msg = "Career profile not found."
        raise NotFoundError(msg)

    revision_ids = select(ProfileRevision.profile_revision_id).where(
        ProfileRevision.career_profile_id == career_profile_id
    )
    intent_ids = select(SearchIntent.search_intent_id).where(
        SearchIntent.career_profile_id == career_profile_id
    )

    async def count(query: Select[Any]) -> int:
        statement = select(func.count()).select_from(query.subquery())
        return int((await session.execute(statement)).scalar_one())

    counts = {
        "profile_revision": await count(revision_ids),
        "search_intent": await count(intent_ids),
        "intent_revision": await count(
            select(IntentRevision.intent_revision_id).where(
                IntentRevision.search_intent_id.in_(intent_ids)
            )
        ),
        "match_evaluation": await count(
            select(MatchEvaluation.match_evaluation_id).where(
                MatchEvaluation.profile_revision_id.in_(revision_ids)
            )
        ),
        "profile_proposal": await count(
            select(ProfileProposal.profile_proposal_id).where(
                ProfileProposal.career_profile_id == career_profile_id
            )
        ),
        "trend_weekly": await count(
            select(TrendWeekly.trend_weekly_id).where(TrendWeekly.search_intent_id.in_(intent_ids))
        ),
    }

    # Evidence of this profile's proposals, and the documents only these proposals used.
    evidence_ids = [
        int(i)
        for i in (
            await session.execute(
                select(ProposalItem.evidence_id)
                .join(
                    ProfileProposal,
                    ProfileProposal.profile_proposal_id == ProposalItem.profile_proposal_id,
                )
                .where(
                    ProfileProposal.career_profile_id == career_profile_id,
                    ProposalItem.evidence_id.is_not(None),
                )
            )
        ).scalars()
        if i is not None
    ]
    mine = select(ProfileProposal.document_id).where(
        ProfileProposal.career_profile_id == career_profile_id,
        ProfileProposal.document_id.is_not(None),
    )
    elsewhere = select(ProfileProposal.document_id).where(
        ProfileProposal.career_profile_id != career_profile_id,
        ProfileProposal.document_id.is_not(None),
    )
    document_ids = [
        int(i)
        for i in (
            await session.execute(
                select(Document.document_id).where(
                    Document.document_id.in_(mine), Document.document_id.not_in(elsewhere)
                )
            )
        ).scalars()
    ]
    counts["evidence"] = len(evidence_ids)
    counts["document"] = len(document_ids)

    async with allow_mutation(session):
        # Break the circular "current revision" pointers first, then let the cascades do the rest.
        await session.execute(
            update(SearchIntent)
            .where(SearchIntent.career_profile_id == career_profile_id)
            .values(current_intent_revision_id=None)
        )
        await session.execute(
            update(CareerProfile)
            .where(CareerProfile.career_profile_id == career_profile_id)
            .values(current_profile_revision_id=None)
        )
        await session.execute(
            text("DELETE FROM career_profile WHERE career_profile_id = :id"),
            {"id": career_profile_id},
        )
        if evidence_ids:
            await session.execute(delete(Evidence).where(Evidence.evidence_id.in_(evidence_ids)))
        if document_ids:
            await session.execute(delete(Evidence).where(Evidence.document_id.in_(document_ids)))
            await session.execute(delete(Document).where(Document.document_id.in_(document_ids)))

    counts["career_profile"] = 1
    session.add(
        AuditEvent(
            owner_id=owner_id,
            action="career_profile_deleted",
            subject_type="career_profile",
            metadata_json={"career_profile_id": career_profile_id, "deleted_counts": counts},
        )
    )
    await session.flush()
    return counts
