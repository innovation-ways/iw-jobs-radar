"""Search intent use cases: create, save as the next revision, enable, history, restore (T3.1)."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import ConflictError, InputValidationError
from jobs_radar.db.models import IntentRevision, SearchIntent
from jobs_radar.repositories.revisions import IntentRepository
from jobs_radar.repositories.taxonomy import TaxonomyRepository
from jobs_radar.schemas.intent import IntentDefinition, validate_intent_against_taxonomy


@dataclass(frozen=True)
class IntentView:
    """An intent with its current revision (``None`` only transiently, before revision 1)."""

    intent: SearchIntent
    current: IntentRevision | None


@dataclass(frozen=True)
class IntentSaveResult:
    """Outcome of a save: the intent as it is now and whether a new revision was created."""

    view: IntentView
    created: bool


class IntentService:
    """Use cases around search intents. The caller owns the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._intents = IntentRepository(session)
        self._taxonomy = TaxonomyRepository(session)

    async def _view(self, intent: SearchIntent) -> IntentView:
        return IntentView(intent, await self._intents.current_revision(intent))

    async def _validate(self, definition: IntentDefinition) -> None:
        """Reject keys that are not in the live taxonomy and closed groups that skip options."""
        errors = validate_intent_against_taxonomy(definition, await self._taxonomy.keys_by_kind())
        if errors:
            msg = "The intent does not match the taxonomy."
            raise InputValidationError(msg, details={"errors": errors})

    async def create(
        self,
        owner_id: int,
        career_profile_id: int,
        definition: IntentDefinition,
        *,
        enabled: bool,
    ) -> IntentView:
        """Create an intent with revision 1."""
        await self._validate(definition)
        intent = await self._intents.create(
            owner_id=owner_id, career_profile_id=career_profile_id, title=definition.title
        )
        intent.enabled = enabled
        await self._intents.add_revision(
            intent, definition=definition, expected_current_revision=None
        )
        await self._session.refresh(intent)
        return await self._view(intent)

    async def list_for_profile(self, owner_id: int, career_profile_id: int) -> list[IntentView]:
        """Return a profile's intents with their current revisions."""
        intents = await self._intents.list_for_profile(owner_id, career_profile_id)
        return [await self._view(intent) for intent in intents]

    async def get(self, owner_id: int, search_intent_id: int) -> IntentView:
        """Return one intent with its current revision."""
        return await self._view(await self._intents.get(owner_id, search_intent_id))

    async def revisions(self, owner_id: int, search_intent_id: int) -> list[IntentRevision]:
        """Return the intent's history, newest first."""
        intent = await self._intents.get(owner_id, search_intent_id)
        return await self._intents.list_revisions(intent)

    async def revision(
        self, owner_id: int, search_intent_id: int, intent_revision_id: int
    ) -> IntentRevision:
        """Return one revision of the intent."""
        intent = await self._intents.get(owner_id, search_intent_id)
        return await self._intents.get_revision(intent, intent_revision_id)

    async def _store(
        self,
        intent: SearchIntent,
        definition: IntentDefinition,
        expected: int,
        change_summary: str | None,
    ) -> IntentSaveResult:
        """Append a revision unless it would repeat the current one."""
        current = await self._intents.current_revision(intent)
        if current is not None and current.intent_json == definition.model_dump(mode="json"):
            return IntentSaveResult(IntentView(intent, current), created=False)
        await self._intents.add_revision(
            intent,
            definition=definition,
            expected_current_revision=expected,
            change_summary=change_summary,
        )
        intent.title = definition.title  # the row title mirrors the current revision's title
        await self._session.flush()
        await self._session.refresh(intent)
        return IntentSaveResult(await self._view(intent), created=True)

    async def _lock_current(
        self, owner_id: int, search_intent_id: int, expected: int
    ) -> SearchIntent:
        intent = await self._intents.get(owner_id, search_intent_id, for_update=True)
        current = await self._intents.current_revision(intent)
        actual = current.revision_number if current else None
        if expected != actual:
            msg = "The intent changed since it was loaded."
            raise ConflictError(msg, details={"expected": expected, "actual": actual})
        return intent

    async def save(
        self,
        owner_id: int,
        search_intent_id: int,
        definition: IntentDefinition,
        *,
        expected_current_revision: int,
        change_summary: str | None = None,
    ) -> IntentSaveResult:
        """Save the intent as its next revision; nothing is created if nothing changed.

        Raises:
            NotFoundError: unknown or foreign intent.
            ConflictError: ``expected_current_revision`` is not the current revision number.
            InputValidationError: the definition does not match the taxonomy.
        """
        intent = await self._lock_current(owner_id, search_intent_id, expected_current_revision)
        await self._validate(definition)
        return await self._store(intent, definition, expected_current_revision, change_summary)

    async def restore(
        self,
        owner_id: int,
        search_intent_id: int,
        intent_revision_id: int,
        *,
        expected_current_revision: int,
    ) -> IntentSaveResult:
        """Make an old revision's content the next revision (history is never rewritten)."""
        intent = await self._lock_current(owner_id, search_intent_id, expected_current_revision)
        old = await self._intents.get_revision(intent, intent_revision_id)
        return await self._store(
            intent,
            IntentDefinition.model_validate(old.intent_json),
            expected_current_revision,
            f"Restored revision {old.revision_number}",
        )

    async def set_enabled(
        self, owner_id: int, search_intent_id: int, *, enabled: bool, expected_version: int
    ) -> IntentView:
        """Enable or disable the intent using the row version the caller saw."""
        intent = await self._intents.get(owner_id, search_intent_id)
        await self._intents.set_enabled(intent, enabled=enabled, expected_version=expected_version)
        return await self._view(intent)
