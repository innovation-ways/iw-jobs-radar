"""Profiles, intents and their immutable revisions (LLD sections 2 and 7).

A new revision is only created when the caller states which revision it was looking at
(``expected_current_revision``); a stale expectation is a conflict (HTTP 409) and changes nothing.
The profile or intent row is locked while the next number is computed, so two concurrent saves
cannot both succeed.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import ConflictError, NotFoundError
from jobs_radar.db.models import (
    CareerProfile,
    IntentRevision,
    ProfileRevision,
    SearchIntent,
)
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.profile import ProfileFacts, ProfilePrivacy


def _check_expected(expected: int | None, actual: int | None, what: str) -> None:
    """Raise a conflict when the caller's view of the current revision is out of date."""
    if expected != actual:
        msg = f"The {what} changed since it was loaded."
        raise ConflictError(msg, details={"expected": expected, "actual": actual})


class ProfileRepository:
    """Data access for career profiles and their revisions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, owner_id: int, title: str) -> CareerProfile:
        """Create a profile without revisions."""
        profile = CareerProfile(owner_id=owner_id, title=title)
        self._session.add(profile)
        await self._session.flush()
        return profile

    async def get(
        self, owner_id: int, career_profile_id: int, *, for_update: bool = False
    ) -> CareerProfile:
        """Return the owner's profile; raises ``NotFoundError`` for unknown or foreign ids."""
        statement = select(CareerProfile).where(
            CareerProfile.career_profile_id == career_profile_id, CareerProfile.owner_id == owner_id
        )
        if for_update:
            statement = statement.with_for_update()
        profile = (await self._session.execute(statement)).scalar_one_or_none()
        if profile is None:
            msg = "Career profile not found."
            raise NotFoundError(msg)
        return profile

    async def list_for_owner(self, owner_id: int) -> list[CareerProfile]:
        """Return the owner's profiles, oldest first."""
        result = await self._session.execute(
            select(CareerProfile)
            .where(CareerProfile.owner_id == owner_id)
            .order_by(CareerProfile.career_profile_id)
        )
        return list(result.scalars())

    async def current_revision(self, profile: CareerProfile) -> ProfileRevision | None:
        """Return the profile's current revision, or ``None`` before the first one."""
        if profile.current_profile_revision_id is None:
            return None
        return await self._session.get(ProfileRevision, profile.current_profile_revision_id)

    async def list_revisions(self, profile: CareerProfile) -> list[ProfileRevision]:
        """Return all revisions of the profile, newest first."""
        rows = await self._session.execute(
            select(ProfileRevision)
            .where(ProfileRevision.career_profile_id == profile.career_profile_id)
            .order_by(ProfileRevision.revision_number.desc())
        )
        return list(rows.scalars())

    async def get_revision(
        self, profile: CareerProfile, profile_revision_id: int
    ) -> ProfileRevision:
        """Return one revision of the profile; ``NotFoundError`` if it is another profile's."""
        revision = (
            await self._session.execute(
                select(ProfileRevision).where(
                    ProfileRevision.profile_revision_id == profile_revision_id,
                    ProfileRevision.career_profile_id == profile.career_profile_id,
                )
            )
        ).scalar_one_or_none()
        if revision is None:
            msg = "Profile revision not found."
            raise NotFoundError(msg)
        return revision

    async def add_revision(
        self,
        profile: CareerProfile,
        *,
        facts: ProfileFacts,
        privacy: ProfilePrivacy,
        expected_current_revision: int | None,
        change_summary: str | None = None,
    ) -> ProfileRevision:
        """Append the next revision and make it current.

        Args:
            profile: The profile; it is locked and refreshed inside this call.
            facts: Validated profile facts.
            privacy: Privacy settings in force.
            expected_current_revision: Revision number the caller saw, or ``None`` if it saw none.
            change_summary: Optional short description of the change.

        Raises:
            ConflictError: If ``expected_current_revision`` is not the current revision number.
        """
        await self._session.refresh(profile, with_for_update=True)
        current = await self.current_revision(profile)
        actual = current.revision_number if current else None
        _check_expected(expected_current_revision, actual, "profile")

        revision = ProfileRevision(
            career_profile_id=profile.career_profile_id,
            revision_number=(actual or 0) + 1,
            facts_json=facts.model_dump(mode="json"),
            privacy_json=privacy.model_dump(mode="json"),
            change_summary=change_summary,
        )
        self._session.add(revision)
        await self._session.flush()
        profile.current_profile_revision_id = revision.profile_revision_id
        profile.version += 1
        await self._session.flush()
        return revision


class IntentRepository:
    """Data access for search intents and their revisions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, owner_id: int, career_profile_id: int, title: str) -> SearchIntent:
        """Create an intent for one of the owner's profiles, without revisions."""
        await ProfileRepository(self._session).get(owner_id, career_profile_id)  # ownership check
        intent = SearchIntent(owner_id=owner_id, career_profile_id=career_profile_id, title=title)
        self._session.add(intent)
        await self._session.flush()
        return intent

    async def get(
        self, owner_id: int, search_intent_id: int, *, for_update: bool = False
    ) -> SearchIntent:
        """Return the owner's intent; raises ``NotFoundError`` for unknown or foreign ids."""
        statement = select(SearchIntent).where(
            SearchIntent.search_intent_id == search_intent_id, SearchIntent.owner_id == owner_id
        )
        if for_update:
            statement = statement.with_for_update()
        intent = (await self._session.execute(statement)).scalar_one_or_none()
        if intent is None:
            msg = "Search intent not found."
            raise NotFoundError(msg)
        return intent

    async def current_revision(self, intent: SearchIntent) -> IntentRevision | None:
        """Return the intent's current revision, or ``None`` before the first one."""
        if intent.current_intent_revision_id is None:
            return None
        return await self._session.get(IntentRevision, intent.current_intent_revision_id)

    async def list_for_profile(self, owner_id: int, career_profile_id: int) -> list[SearchIntent]:
        """Return the intents of one of the owner's profiles, oldest first."""
        await ProfileRepository(self._session).get(owner_id, career_profile_id)  # ownership check
        rows = await self._session.execute(
            select(SearchIntent)
            .where(
                SearchIntent.owner_id == owner_id,
                SearchIntent.career_profile_id == career_profile_id,
            )
            .order_by(SearchIntent.search_intent_id)
        )
        return list(rows.scalars())

    async def list_enabled(self, owner_id: int) -> list[SearchIntent]:
        """Return the owner's enabled intents, oldest first."""
        rows = await self._session.execute(
            select(SearchIntent)
            .where(SearchIntent.owner_id == owner_id, SearchIntent.enabled.is_(True))
            .order_by(SearchIntent.search_intent_id)
        )
        return list(rows.scalars())

    async def list_revisions(self, intent: SearchIntent) -> list[IntentRevision]:
        """Return all revisions of the intent, newest first."""
        rows = await self._session.execute(
            select(IntentRevision)
            .where(IntentRevision.search_intent_id == intent.search_intent_id)
            .order_by(IntentRevision.revision_number.desc())
        )
        return list(rows.scalars())

    async def get_revision(self, intent: SearchIntent, intent_revision_id: int) -> IntentRevision:
        """Return one revision of the intent; ``NotFoundError`` if it belongs to another intent."""
        revision = (
            await self._session.execute(
                select(IntentRevision).where(
                    IntentRevision.intent_revision_id == intent_revision_id,
                    IntentRevision.search_intent_id == intent.search_intent_id,
                )
            )
        ).scalar_one_or_none()
        if revision is None:
            msg = "Intent revision not found."
            raise NotFoundError(msg)
        return revision

    async def add_revision(
        self,
        intent: SearchIntent,
        *,
        definition: IntentDefinition,
        expected_current_revision: int | None,
        change_summary: str | None = None,
    ) -> IntentRevision:
        """Append the next revision and make it current (same rules as for profiles).

        Raises:
            ConflictError: If ``expected_current_revision`` is not the current revision number.
        """
        await self._session.refresh(intent, with_for_update=True)
        current = await self.current_revision(intent)
        actual = current.revision_number if current else None
        _check_expected(expected_current_revision, actual, "intent")

        revision = IntentRevision(
            search_intent_id=intent.search_intent_id,
            revision_number=(actual or 0) + 1,
            intent_json=definition.model_dump(mode="json"),
            change_summary=change_summary,
        )
        self._session.add(revision)
        await self._session.flush()
        intent.current_intent_revision_id = revision.intent_revision_id
        intent.version += 1
        await self._session.flush()
        return revision

    async def set_enabled(
        self, intent: SearchIntent, *, enabled: bool, expected_version: int
    ) -> SearchIntent:
        """Enable or disable the intent, checking the row version.

        Raises:
            ConflictError: If ``expected_version`` is not the intent's current version.
        """
        await self._session.refresh(intent, with_for_update=True)
        if intent.version != expected_version:
            msg = "The intent changed since it was loaded."
            raise ConflictError(
                msg, details={"expected": expected_version, "actual": intent.version}
            )
        intent.enabled = enabled
        intent.version += 1
        await self._session.flush()
        return intent
