"""Career profile use cases: create, save as the next revision, history and restore (T3.1).

The profile is canonical (ADR-003): every save either creates the next immutable revision or, when
nothing changed, none at all. Skills are typed by name and resolved to canonical skills here.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import ConflictError
from jobs_radar.db.models import CareerProfile, ProfileRevision
from jobs_radar.domain.enums import EvidenceOrigin
from jobs_radar.domain.skills import normalise_skill_name
from jobs_radar.repositories.revisions import ProfileRepository
from jobs_radar.repositories.skills import SkillRepository
from jobs_radar.schemas.profile import ProfileFacts, ProfilePrivacy, Provenance
from jobs_radar.schemas.profile_api import ProfileInput

# Facts that carry provenance, keyed by the field that holds them in ``ProfileFacts``.
_PROVENANCE_LISTS = ("skills", "experience", "education", "certifications")


@dataclass(frozen=True)
class RevisionView:
    """A revision with the names of the skills it references."""

    revision: ProfileRevision
    skill_names: dict[int, str]


@dataclass(frozen=True)
class ProfileView:
    """A profile with its current revision (``None`` before the first save)."""

    profile: CareerProfile
    current: RevisionView | None


@dataclass(frozen=True)
class SaveResult:
    """Outcome of a save: the revision now current and whether a new one was created."""

    view: RevisionView
    created: bool


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _without_provenance(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key != "provenance"}


class ProfileService:
    """Use cases around profiles. The caller owns the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._profiles = ProfileRepository(session)
        self._skills = SkillRepository(session)

    # --- reading ---------------------------------------------------------------------------

    async def _view(self, revision: ProfileRevision) -> RevisionView:
        ids = {int(skill["skill_id"]) for skill in revision.facts_json.get("skills", [])}
        return RevisionView(revision, await self._skills.names(ids))

    async def _profile_view(self, profile: CareerProfile) -> ProfileView:
        current = await self._profiles.current_revision(profile)
        return ProfileView(profile, await self._view(current) if current else None)

    async def create(self, owner_id: int, title: str) -> ProfileView:
        """Create a blank profile (no revision yet)."""
        profile = await self._profiles.create(owner_id=owner_id, title=title)
        await self._session.refresh(profile)
        return ProfileView(profile, None)

    async def list_profiles(self, owner_id: int) -> list[ProfileView]:
        """Return the owner's profiles with their current revisions."""
        return [await self._profile_view(p) for p in await self._profiles.list_for_owner(owner_id)]

    async def get(self, owner_id: int, career_profile_id: int) -> ProfileView:
        """Return one profile with its current revision."""
        return await self._profile_view(await self._profiles.get(owner_id, career_profile_id))

    async def revisions(self, owner_id: int, career_profile_id: int) -> list[RevisionView]:
        """Return the profile's history, newest first."""
        profile = await self._profiles.get(owner_id, career_profile_id)
        return [await self._view(r) for r in await self._profiles.list_revisions(profile)]

    async def revision(
        self, owner_id: int, career_profile_id: int, profile_revision_id: int
    ) -> RevisionView:
        """Return one revision of the profile."""
        profile = await self._profiles.get(owner_id, career_profile_id)
        return await self._view(await self._profiles.get_revision(profile, profile_revision_id))

    # --- writing ---------------------------------------------------------------------------

    async def _lock_current(
        self, owner_id: int, career_profile_id: int, expected: int | None
    ) -> tuple[CareerProfile, ProfileRevision | None]:
        """Lock the profile and check the caller saw its current revision."""
        profile = await self._profiles.get(owner_id, career_profile_id, for_update=True)
        current = await self._profiles.current_revision(profile)
        actual = current.revision_number if current else None
        if expected != actual:
            msg = "The profile changed since it was loaded."
            raise ConflictError(msg, details={"expected": expected, "actual": actual})
        return profile, current

    async def _build_facts(
        self, data: ProfileInput, previous: dict[str, Any] | None, now: datetime
    ) -> ProfileFacts:
        """Resolve skill names and attach provenance, reusing it for items that did not change."""
        skill_ids = {
            skill.name: (await self._skills.resolve_or_create(skill.name, skill.kind)).skill_id
            for skill in data.skills
        }
        raw: dict[str, Any] = data.model_dump(mode="json", exclude={"privacy", "skills"})
        raw["skills"] = [
            {"skill_id": skill_ids[s.name], "level": s.level, "years": s.years} for s in data.skills
        ]
        manual = Provenance(origin=EvidenceOrigin.MANUAL, accepted_at=now).model_dump(mode="json")
        for field in _PROVENANCE_LISTS:
            old = [
                (_without_provenance(i), i["provenance"]) for i in (previous or {}).get(field, [])
            ]
            merged = []
            for item in raw[field]:
                match = next((prov for content, prov in old if content == item), None)
                merged.append({**item, "provenance": match or manual})
            raw[field] = merged
        return ProfileFacts.model_validate(raw)

    async def _store(
        self,
        profile: CareerProfile,
        current: ProfileRevision | None,
        facts: ProfileFacts,
        privacy: ProfilePrivacy,
        change_summary: str | None,
    ) -> SaveResult:
        """Append a revision unless it would repeat the current one."""
        facts_json, privacy_json = facts.model_dump(mode="json"), privacy.model_dump(mode="json")
        if current is not None and (current.facts_json, current.privacy_json) == (
            facts_json,
            privacy_json,
        ):
            return SaveResult(await self._view(current), created=False)
        revision = await self._profiles.add_revision(
            profile,
            facts=facts,
            privacy=privacy,
            expected_current_revision=current.revision_number if current else None,
            change_summary=change_summary,
        )
        return SaveResult(await self._view(revision), created=True)

    async def save(
        self,
        owner_id: int,
        career_profile_id: int,
        data: ProfileInput,
        *,
        expected_current_revision: int | None,
        change_summary: str | None = None,
    ) -> SaveResult:
        """Save the profile as its next revision; nothing is created if nothing changed.

        Raises:
            NotFoundError: unknown or foreign profile.
            ConflictError: ``expected_current_revision`` is not the current revision number.
        """
        profile, current = await self._lock_current(
            owner_id, career_profile_id, expected_current_revision
        )
        facts = await self._build_facts(data, current.facts_json if current else None, _utc_now())
        return await self._store(profile, current, facts, data.privacy, change_summary)

    async def restore(
        self,
        owner_id: int,
        career_profile_id: int,
        profile_revision_id: int,
        *,
        expected_current_revision: int,
    ) -> SaveResult:
        """Make an old revision's content the next revision (history is never rewritten)."""
        profile, current = await self._lock_current(
            owner_id, career_profile_id, expected_current_revision
        )
        old = await self._profiles.get_revision(profile, profile_revision_id)
        return await self._store(
            profile,
            current,
            ProfileFacts.model_validate(old.facts_json),
            ProfilePrivacy.model_validate(old.privacy_json),
            f"Restored revision {old.revision_number}",
        )

    # --- reviewed imports ------------------------------------------------------------------

    async def lock_current(
        self, owner_id: int, career_profile_id: int, expected: int | None
    ) -> tuple[CareerProfile, RevisionView | None]:
        """Lock the profile, check the caller saw its current revision and return it."""
        profile, current = await self._lock_current(owner_id, career_profile_id, expected)
        return profile, (await self._view(current) if current else None)

    async def save_reviewed(
        self,
        profile: CareerProfile,
        current: RevisionView | None,
        data: ProfileInput,
        accepted: dict[str, dict[str, Provenance]],
        change_summary: str | None,
    ) -> SaveResult:
        """Save ``data`` as the next revision, marking accepted items with their provenance.

        ``accepted`` maps a list field (``skills``, ``experience``, ``education``,
        ``certifications``) to ``{item key: provenance}``. An item whose content is unchanged
        keeps the provenance it already had.
        """
        previous = current.revision.facts_json if current else None
        facts = await self._build_facts(data, previous, _utc_now())
        facts_json = facts.model_dump(mode="json")
        names = await self._skills.names({s["skill_id"] for s in facts_json["skills"]})
        before = {
            field: [_without_provenance(i) for i in (previous or {}).get(field, [])]
            for field in _PROVENANCE_LISTS
        }
        for field, by_key in accepted.items():
            for item in facts_json[field]:
                content = _without_provenance(item)
                if content in before[field]:
                    continue
                provenance = by_key.get(item_key(field, item, names))
                if provenance is not None:
                    item["provenance"] = provenance.model_dump(mode="json")
        return await self._store(
            profile,
            current.revision if current else None,
            ProfileFacts.model_validate(facts_json),
            data.privacy,
            change_summary,
        )


def item_key(field: str, item: dict[str, Any], skill_names: dict[int, str]) -> str:
    """Return a stable key identifying a list item inside its field (to merge reviewed items)."""
    if field == "skills":
        return normalise_skill_name(skill_names[item["skill_id"]])
    if field == "experience":
        return f"{item['title']}|{item['organisation']}|{item['start']}".casefold()
    if field == "education":
        return f"{item['level']}|{item['field']}".casefold()
    return str(item["name"]).casefold()  # certifications
