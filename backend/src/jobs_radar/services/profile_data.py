"""Export and confirmed deletion of a profile's data (UC-08, T6.6).

The export adds to the profile and intents (see the profile routes) the history the owner
created: every profile and intent revision, imported-document *metadata*, proposals with their
reviewed items and the owner's inbox decisions. It never contains a credential, a provider
setup, an original CV or CV text.
Deletion needs the profile title typed back, removes the data through the audited path and keeps
only an audit event with counts.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import InputValidationError
from jobs_radar.db.models import (
    AuditEvent,
    Document,
    IntentRevision,
    JobInboxItem,
    ProfileProposal,
    ProfileRevision,
    ProposalItem,
    SearchIntent,
)
from jobs_radar.repositories.deletion import delete_career_profile
from jobs_radar.repositories.revisions import ProfileRepository


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


class ProfileDataService:
    """Export and delete a profile's data. The caller owns the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._profiles = ProfileRepository(session)

    async def history(self, owner_id: int, career_profile_id: int) -> dict[str, Any]:
        """Return the history sections of the export and record that an export happened."""
        await self._profiles.get(owner_id, career_profile_id)
        revisions = (
            await self._session.execute(
                select(ProfileRevision)
                .where(ProfileRevision.career_profile_id == career_profile_id)
                .order_by(ProfileRevision.revision_number)
            )
        ).scalars()
        intents = (
            await self._session.execute(
                select(SearchIntent)
                .where(SearchIntent.career_profile_id == career_profile_id)
                .order_by(SearchIntent.search_intent_id)
            )
        ).scalars()
        intent_rows = [(i, await self._intent_revisions(i.search_intent_id)) for i in intents]
        proposals = list(
            (
                await self._session.execute(
                    select(ProfileProposal)
                    .where(ProfileProposal.career_profile_id == career_profile_id)
                    .order_by(ProfileProposal.profile_proposal_id)
                )
            ).scalars()
        )
        document_ids = {p.document_id for p in proposals if p.document_id is not None}
        documents: list[Document] = []
        if document_ids:
            documents = list(
                (
                    await self._session.execute(
                        select(Document)
                        .where(
                            Document.owner_id == owner_id, Document.document_id.in_(document_ids)
                        )
                        .order_by(Document.document_id)
                    )
                ).scalars()
            )
        inbox = (
            await self._session.execute(
                select(JobInboxItem)
                .where(JobInboxItem.owner_id == owner_id)
                .order_by(JobInboxItem.job_inbox_item_id)
            )
        ).scalars()

        export: dict[str, Any] = {
            "revisions": [
                {
                    "revision_number": r.revision_number,
                    "created_at": _iso(r.created_at),
                    "change_summary": r.change_summary,
                    "facts": r.facts_json,
                    "privacy": r.privacy_json,
                }
                for r in revisions
            ],
            "intent_revisions": [
                {
                    "intent_title": i.title,
                    "revision_number": r.revision_number,
                    "created_at": _iso(r.created_at),
                    "change_summary": r.change_summary,
                    "intent": r.intent_json,
                }
                for i, rows in intent_rows
                for r in rows
            ],
            "documents": [
                {
                    "document_id": d.document_id,
                    "sha256": d.sha256,
                    "mime_type": d.mime_type,
                    "byte_size": d.byte_size,
                    "extraction_status": d.extraction_status,
                    "uploaded_at": _iso(d.created_at),
                }
                for d in documents
            ],
            "proposals": [await self._proposal(p) for p in proposals],
            "inbox": [
                {
                    "job_opportunity_id": item.job_opportunity_id,
                    "state": item.state,
                    "is_shortlisted": item.is_shortlisted,
                    "note": item.note,
                    "applied_at": _iso(item.applied_at),
                    "application_url": item.application_url,
                }
                for item in inbox
            ],
        }
        self._session.add(
            AuditEvent(
                owner_id=owner_id,
                action="career_profile_exported",
                subject_type="career_profile",
                metadata_json={
                    "career_profile_id": career_profile_id,
                    "counts": {
                        "revisions": len(export["revisions"]),
                        "intent_revisions": len(export["intent_revisions"]),
                        "documents": len(export["documents"]),
                        "proposals": len(export["proposals"]),
                        "inbox": len(export["inbox"]),
                    },
                },
            )
        )
        await self._session.flush()
        return export

    async def _intent_revisions(self, search_intent_id: int) -> list[IntentRevision]:
        rows = await self._session.execute(
            select(IntentRevision)
            .where(IntentRevision.search_intent_id == search_intent_id)
            .order_by(IntentRevision.revision_number)
        )
        return list(rows.scalars())

    async def _proposal(self, proposal: ProfileProposal) -> dict[str, Any]:
        items = (
            await self._session.execute(
                select(ProposalItem)
                .where(ProposalItem.profile_proposal_id == proposal.profile_proposal_id)
                .order_by(ProposalItem.proposal_item_id)
            )
        ).scalars()
        return {
            "profile_proposal_id": proposal.profile_proposal_id,
            "document_id": proposal.document_id,
            "provider_type": proposal.provider_type,
            "provider_model": proposal.provider_model,
            "prompt_version": proposal.prompt_version,
            "redaction_policy": proposal.redaction_policy,
            "consent": proposal.consent_json,
            "status": proposal.status,
            "created_at": _iso(proposal.created_at),
            "items": [
                {
                    "path": i.path,
                    "value": i.value_json,
                    "edited_value": i.edited_value_json,
                    "source_excerpt": i.source_excerpt,
                    "confidence": float(i.confidence) if i.confidence is not None else None,
                    "review_status": i.review_status,
                }
                for i in items
            ],
        }

    async def delete(
        self, owner_id: int, career_profile_id: int, *, confirm: str
    ) -> dict[str, int]:
        """Delete the profile and what hangs off it; ``confirm`` must be the exact title.

        Raises:
            NotFoundError: unknown profile.
            InputValidationError: ``confirm`` is not the profile title (``confirmation_mismatch``).
        """
        profile = await self._profiles.get(owner_id, career_profile_id)
        if confirm != profile.title:
            msg = "Type the exact profile title to confirm the deletion."
            raise InputValidationError(msg, details={"error_class": "confirmation_mismatch"})
        return await delete_career_profile(
            self._session, owner_id=owner_id, career_profile_id=career_profile_id
        )
