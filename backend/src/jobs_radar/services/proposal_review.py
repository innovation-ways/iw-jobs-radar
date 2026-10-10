"""Reviewing a proposal: accept, edit, reject or defer items, then apply them atomically (T6.5).

All decisions are validated first and applied inside one savepoint together with the new profile
revision and the evidence rows, so an error leaves no half-applied review. Only accepted and edited
items become facts; rejected and deferred items stay as audit data and never reach a revision.
Facts from a document carry ``origin = document`` and the evidence (excerpt, confidence, document).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import ConflictError, InputValidationError, NotFoundError
from jobs_radar.db.models import Evidence, ProfileProposal, ProposalItem
from jobs_radar.domain.enums import EvidenceOrigin
from jobs_radar.domain.skills import normalise_skill_name
from jobs_radar.schemas.profile import BaseLocation, ProfilePrivacy, Provenance
from jobs_radar.schemas.profile_api import ProfileInput
from jobs_radar.services.locations import load_gazetteer
from jobs_radar.services.profiles import ProfileService, RevisionView
from jobs_radar.services.proposal_rules import SINGLE_PATHS, validate_value

DecisionKind = Literal["accept", "edit", "reject", "defer"]
_STATUS = {"accept": "accepted", "edit": "edited", "reject": "rejected", "defer": "deferred"}
_OPEN = {"pending", "deferred"}
_LIST_PROVENANCE = ("skills", "experience", "education", "certifications")


@dataclass(frozen=True)
class Decision:
    """The owner's decision on one proposal item; ``value`` is required for ``edit``."""

    proposal_item_id: int
    decision: DecisionKind
    value: Any = None


@dataclass(frozen=True)
class ReviewResult:
    """What a review did: the current revision and whether a new one was created."""

    created: bool
    revision_number: int
    view: RevisionView | None
    proposal: ProfileProposal
    items: list[ProposalItem]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _blank() -> dict[str, Any]:
    return {
        "headline": None,
        "base_location": None,
        "years_experience": None,
        "languages": [],
        "skills": [],
        "experience": [],
        "education": [],
        "certifications": [],
    }


class ReviewService:
    """Applies the owner's review of a proposal. The caller owns the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._profiles = ProfileService(session)

    # --- loading and validating --------------------------------------------------------------

    async def _load(
        self, owner_id: int, career_profile_id: int, profile_proposal_id: int
    ) -> tuple[ProfileProposal, dict[int, ProposalItem]]:
        proposal = (
            await self._session.execute(
                select(ProfileProposal)
                .where(
                    ProfileProposal.owner_id == owner_id,
                    ProfileProposal.profile_proposal_id == profile_proposal_id,
                    ProfileProposal.career_profile_id == career_profile_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if proposal is None:
            msg = f"Proposal {profile_proposal_id} does not exist for this profile."
            raise NotFoundError(msg)
        items = (
            await self._session.execute(
                select(ProposalItem).where(ProposalItem.profile_proposal_id == profile_proposal_id)
            )
        ).scalars()
        return proposal, {i.proposal_item_id: i for i in items}

    @staticmethod
    def _resolved_place(raw: Any) -> dict[str, Any]:
        """Turn a stated place into a base location (offline GeoNames), or ask for an edit."""
        if isinstance(raw, dict) and "timezone" in raw:
            return BaseLocation.model_validate(raw).model_dump(mode="json")
        place = load_gazetteer().resolve(str(raw["place"]), country=str(raw["country"]))
        if place is None:
            msg = (
                f"Could not resolve the place '{raw['place']}'. Edit the place "
                "(a larger city nearby, or add its time zone)."
            )
            raise InputValidationError(msg)
        return {
            "place": place.label,
            "country": place.country,
            "timezone": place.timezone,
            "latitude": place.latitude,
            "longitude": place.longitude,
        }

    def _value_for(self, item: ProposalItem, decision: Decision) -> Any:
        """Validate the value that would become a fact (the proposed one, or the edit)."""
        if decision.decision == "edit":
            if decision.value is None:
                msg = f"Item {item.proposal_item_id}: an edit needs a value."
                raise InputValidationError(msg)
            raw = decision.value
        else:
            raw = item.value_json
        try:
            if item.path == "base_location" and isinstance(raw, dict) and "timezone" in raw:
                return self._resolved_place(raw)
            value = validate_value(item.path, raw)
        except (ValidationError, ValueError, TypeError) as error:
            msg = f"Item {item.proposal_item_id} ({item.path}) is not valid: {error}"
            raise InputValidationError(msg) from error
        return self._resolved_place(value) if item.path == "base_location" else value

    # --- merging -------------------------------------------------------------------------------

    @staticmethod
    def _base_input(view: RevisionView | None) -> tuple[dict[str, Any], ProfilePrivacy]:
        if view is None:
            return _blank(), ProfilePrivacy()
        facts = view.revision.facts_json
        base = {
            "headline": facts["headline"],
            "base_location": facts["base_location"],
            "years_experience": facts["years_experience"],
            "languages": list(facts["languages"]),
            "skills": [
                {
                    "name": view.skill_names[s["skill_id"]],
                    "level": s["level"],
                    "years": s["years"],
                }
                for s in facts["skills"]
            ],
            "experience": [
                {k: v for k, v in e.items() if k != "provenance"} for e in facts["experience"]
            ],
            "education": [
                {k: v for k, v in e.items() if k != "provenance"} for e in facts["education"]
            ],
            "certifications": [
                {k: v for k, v in c.items() if k != "provenance"} for c in facts["certifications"]
            ],
            # Typed by the owner, never proposed by an import: carried over unchanged (ADR-057).
            "directions": list(facts.get("directions", [])),
        }
        return base, ProfilePrivacy.model_validate(view.revision.privacy_json)

    @staticmethod
    def _key(path: str, value: dict[str, Any]) -> str:
        if path == "skills":
            return normalise_skill_name(value["name"])
        if path == "languages":
            return str(value["language"])
        if path == "experience":
            return f"{value['title']}|{value['organisation']}|{value['start']}".casefold()
        if path == "education":
            return f"{value['level']}|{value['field']}".casefold()
        return str(value["name"]).casefold()

    def _merge(self, base: dict[str, Any], accepted: list[tuple[ProposalItem, Any]]) -> None:
        for item, value in accepted:
            if item.path in SINGLE_PATHS:
                base[item.path] = value
                continue
            entries: list[dict[str, Any]] = base[item.path]
            key = self._key(item.path, value)
            kept = [e for e in entries if self._key(item.path, e) != key]
            base[item.path] = [*kept, value]

    # --- applying -----------------------------------------------------------------------------

    async def review(
        self,
        owner_id: int,
        career_profile_id: int,
        profile_proposal_id: int,
        decisions: list[Decision],
        *,
        expected_current_revision: int | None,
        change_summary: str | None = None,
    ) -> ReviewResult:
        """Apply the decisions: update the items and create revision N+1 if facts changed.

        Raises:
            NotFoundError: unknown proposal, item or profile.
            ConflictError: stale ``expected_current_revision`` or an item that is already decided.
            InputValidationError: an invalid value, a place that cannot be resolved, or a first
                revision without headline, base location and years of experience.
        """
        proposal, items = await self._load(owner_id, career_profile_id, profile_proposal_id)
        seen: set[int] = set()
        chosen: list[tuple[ProposalItem, Decision, Any]] = []
        for decision in decisions:
            item = items.get(decision.proposal_item_id)
            if item is None:
                msg = f"Item {decision.proposal_item_id} is not part of this proposal."
                raise NotFoundError(msg)
            if decision.proposal_item_id in seen:
                msg = f"Item {decision.proposal_item_id} appears twice."
                raise InputValidationError(msg)
            seen.add(decision.proposal_item_id)
            if item.review_status not in _OPEN:
                msg = f"Item {item.proposal_item_id} was already decided."
                raise ConflictError(msg)
            value = (
                self._value_for(item, decision) if decision.decision in {"accept", "edit"} else None
            )
            chosen.append((item, decision, value))

        profile, current = await self._profiles.lock_current(
            owner_id, career_profile_id, expected_current_revision
        )
        accepted = [
            (item, value)
            for item, decision, value in chosen
            if decision.decision in {"accept", "edit"}
        ]
        # Everything below is one unit: an error rolls back items, evidence and revision together.
        async with self._session.begin_nested():
            now = _utc_now()
            created = False
            view = current
            if accepted:
                base, privacy = self._base_input(current)
                self._merge(base, accepted)
                missing = [
                    k for k in ("headline", "base_location", "years_experience") if base[k] is None
                ]
                if missing:
                    msg = (
                        "A first revision needs a headline, a base location and years of "
                        f"experience; missing: {', '.join(m.replace('_', ' ') for m in missing)}."
                    )
                    raise InputValidationError(msg)
                provenance = await self._evidence(owner_id, proposal, accepted, now)
                try:
                    data = ProfileInput.model_validate({**base, "privacy": privacy})
                except ValidationError as error:
                    msg = f"The reviewed profile is not valid: {error.errors()[0]['msg']}."
                    raise InputValidationError(msg) from error
                saved = await self._profiles.save_reviewed(
                    profile, current, data, provenance, change_summary or "Imported from a CV"
                )
                created, view = saved.created, saved.view
            for item, decision, value in chosen:
                item.review_status = _STATUS[decision.decision]
                item.reviewed_at = now
                if decision.decision == "edit":
                    item.edited_value_json = value
            await self._session.flush()
            if not any(i.review_status == "pending" for i in items.values()):
                proposal.status = "completed"
                proposal.completed_at = now
                proposal.version += 1
            await self._session.flush()
        number = view.revision.revision_number if view else 0
        return ReviewResult(created, number, view, proposal, list(items.values()))

    async def _evidence(
        self,
        owner_id: int,
        proposal: ProfileProposal,
        accepted: list[tuple[ProposalItem, Any]],
        now: datetime,
    ) -> dict[str, dict[str, Provenance]]:
        """Create evidence for each accepted item; return provenance keyed like list items."""
        by_field: dict[str, dict[str, Provenance]] = {}
        for item, value in accepted:
            evidence = Evidence(
                owner_id=owner_id,
                origin=EvidenceOrigin.DOCUMENT.value,
                document_id=proposal.document_id,
                excerpt=item.source_excerpt,
                confidence=item.confidence,
                accepted_at=now,
            )
            self._session.add(evidence)
            await self._session.flush()
            item.evidence_id = evidence.evidence_id
            if item.path in _LIST_PROVENANCE:
                by_field.setdefault(item.path, {})[self._key(item.path, value)] = Provenance(
                    origin=EvidenceOrigin.DOCUMENT,
                    evidence_id=evidence.evidence_id,
                    accepted_at=now,
                )
        return by_field
