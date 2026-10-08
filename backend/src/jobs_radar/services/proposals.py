"""Profile proposals from a CV: consent, redaction, generation and review (T6.3, T6.5, ADR-010).

Flow: the text held in memory goes to the connection chosen for CV import. A remote provider needs
the owner's consent for *that* connection and model, and receives text with contact details
removed (unless the owner turned redaction off). There is never a fallback from a local model to a
cloud one: a failure is reported and the owner decides. The answer becomes ``pending`` proposal
items; only the owner's review turns an item into a profile fact.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.core.errors import (
    ConflictError,
    DependencyUnavailableError,
    InputValidationError,
    NotFoundError,
)
from jobs_radar.core.settings import Settings
from jobs_radar.db.models import Document, ProfileProposal, ProposalItem
from jobs_radar.domain.redaction import REDACTION_POLICY, redact_contact_details
from jobs_radar.repositories.revisions import ProfileRepository
from jobs_radar.services.ai_settings import AiSettingsService
from jobs_radar.services.document_store import DocumentTextStore
from jobs_radar.services.proposal_prompt import PROPOSAL_PROMPT_VERSION, build_request
from jobs_radar.services.proposal_rules import parse_draft

_LOCAL = {"ollama"}


@dataclass(frozen=True)
class Consent:
    """What the owner agreed to: send this CV to this connection and model."""

    provider_connection_id: int
    model_id: str


@dataclass(frozen=True)
class ProposalResult:
    """A proposal with its items."""

    proposal: ProfileProposal
    items: list[ProposalItem]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProposalService:
    """Generates proposals from the CV text. The caller owns the transaction."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        store: DocumentTextStore,
        ai: AiSettingsService,
    ) -> None:
        self._session = session
        self._settings = settings
        self._store = store
        self._ai = ai
        self._profiles = ProfileRepository(session)

    async def generate(
        self,
        owner_id: int,
        document_id: int,
        career_profile_id: int,
        *,
        consent: Consent | None,
    ) -> ProposalResult:
        """Ask the chosen model for proposals; nothing is stored unless the answer is usable.

        Raises:
            NotFoundError: unknown profile.
            InputValidationError: no AI connection chosen, or consent missing.
            ConflictError: the text is no longer in memory; upload the CV again.
            DependencyUnavailableError: the provider failed or its answer was unusable.
        """
        await self._profiles.get(owner_id, career_profile_id)
        known = await self._session.scalar(
            select(Document.document_id).where(
                Document.owner_id == owner_id, Document.document_id == document_id
            )
        )
        if known is None:
            msg = f"Document {document_id} does not exist."
            raise NotFoundError(msg)
        text = self._store.get(document_id)
        if text is None:
            msg = "The CV text is no longer available. Upload the CV again."
            raise ConflictError(msg)
        target = await self._ai.import_target(owner_id)
        if target is None:
            msg = "Choose an AI connection for CV import first (AI & privacy)."
            raise InputValidationError(msg)
        connection, provider = target
        remote = connection.provider_type not in _LOCAL
        redact = remote and await self._ai.redaction_enabled(owner_id)
        if remote:
            self._require_consent(connection.provider_connection_id, connection.model_id, consent)

        to_send = redact_contact_details(text).text if redact else text
        request, sent, _truncated = build_request(to_send)
        try:
            output = await provider.extract(request)
        except ProviderError as error:
            raise DependencyUnavailableError(
                error.message, details={"error_class": error.error_class.value}
            ) from error
        draft = parse_draft(output.content, sent)
        if not draft.items:
            msg = "The AI model returned no usable proposals. Try again or use another model."
            raise DependencyUnavailableError(msg, details={"error_class": "invalid_response"})

        proposal = ProfileProposal(
            owner_id=owner_id,
            career_profile_id=career_profile_id,
            document_id=document_id,
            provider_type=connection.provider_type,
            provider_model=connection.model_id,
            prompt_version=PROPOSAL_PROMPT_VERSION,
            redaction_policy=(REDACTION_POLICY if redact else "none") if remote else None,
            consent_json=self._consent_record(connection, redact) if remote else None,
        )
        self._session.add(proposal)
        await self._session.flush()
        items = [
            ProposalItem(
                profile_proposal_id=proposal.profile_proposal_id,
                path=item.path,
                value_json=item.value,
                source_excerpt=item.excerpt,
                confidence=item.confidence,
            )
            for item in draft.items
        ]
        self._session.add_all(items)
        await self._session.flush()
        await self._session.refresh(proposal)
        for item in items:
            await self._session.refresh(item)
        self._store.discard(document_id)  # the original text is not kept (ADR-010)
        return ProposalResult(proposal, items)

    @staticmethod
    def _require_consent(connection_id: int, model_id: str | None, consent: Consent | None) -> None:
        """Consent must name the connection and model that will actually be used."""
        if (
            consent is None
            or consent.provider_connection_id != connection_id
            or consent.model_id != model_id
        ):
            msg = (
                "Sending a CV to a remote provider needs your confirmation for this "
                "provider and model."
            )
            raise InputValidationError(msg, details={"error_class": "consent_required"})

    @staticmethod
    def _consent_record(connection: Any, redacted: bool) -> dict[str, Any]:
        """Describe what was agreed, for the audit trail (no credential, no content)."""
        return {
            "provider_connection_id": connection.provider_connection_id,
            "provider_type": connection.provider_type,
            "model_id": connection.model_id,
            "processing_location": "remote",
            "content_category": "cv",
            "purpose": "Propose profile facts from the CV for the owner's review",
            "redacted": redacted,
            "redaction_policy": REDACTION_POLICY if redacted else "none",
            "confirmed_at": _utc_now().isoformat(),
        }

    async def get(self, owner_id: int, profile_proposal_id: int) -> ProposalResult:
        """Return a proposal with its items."""
        proposal = (
            await self._session.execute(
                select(ProfileProposal).where(
                    ProfileProposal.owner_id == owner_id,
                    ProfileProposal.profile_proposal_id == profile_proposal_id,
                )
            )
        ).scalar_one_or_none()
        if proposal is None:
            msg = f"Proposal {profile_proposal_id} does not exist."
            raise NotFoundError(msg)
        items = (
            await self._session.execute(
                select(ProposalItem)
                .where(ProposalItem.profile_proposal_id == profile_proposal_id)
                .order_by(ProposalItem.proposal_item_id)
            )
        ).scalars()
        return ProposalResult(proposal, list(items))
