"""Where the owner can work, derived from the profile and the enabled search intents (ADR-049.11).

Job-board filters never take countries from the sources screen: the base location the owner wrote
in the profile and the regions where remote work is acceptable in each enabled intent are the only
inputs. The caller owns the session.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import CareerProfile
from jobs_radar.domain.job_board_rules import (
    LocationPreference,
    LocationScope,
    derive_location_scope,
)
from jobs_radar.repositories.revisions import IntentRepository, ProfileRepository
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.profile import ProfileFacts

_REMOTE = "remote"
_LOCAL = ("hybrid", "onsite")


def _acceptable(definition: IntentDefinition, keys: tuple[str, ...]) -> bool:
    """Whether any of the work arrangements ``keys`` is listed and not rejected."""
    return any(
        entry.key in keys and entry.stance.value != "rejected"
        for entry in definition.stances.work_arrangements
    )


class LocationScopeService:
    """Builds the :class:`LocationScope` of an owner from stored revisions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._intents = IntentRepository(session)
        self._profiles = ProfileRepository(session)

    async def for_owner(self, owner_id: int) -> LocationScope:
        """Return the scope of the owner's enabled intents (empty when there are none)."""
        preferences: list[LocationPreference] = []
        for intent in await self._intents.list_enabled(owner_id):
            revision = await self._intents.current_revision(intent)
            if revision is None:
                continue
            definition = IntentDefinition.model_validate(revision.intent_json)
            preferences.append(
                LocationPreference(
                    base_country=await self._base_country(intent.career_profile_id),
                    remote_regions=definition.work_rules.remote.eligible_regions,
                    remote_acceptable=_acceptable(definition, (_REMOTE,)),
                    local_acceptable=_acceptable(definition, _LOCAL),
                )
            )
        return derive_location_scope(preferences)

    async def _base_country(self, career_profile_id: int) -> str | None:
        """Country of the base location in the profile's current revision, if it has one."""
        profile = await self._session.get(CareerProfile, career_profile_id)
        if profile is None:
            return None
        revision = await self._profiles.current_revision(profile)
        if revision is None:
            return None
        return ProfileFacts.model_validate(revision.facts_json).base_location.country
