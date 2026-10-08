"""Inbox items and their append-only event stream (LLD sections 3 and 7; ADR-006).

This layer only offers safe primitives: optimistic version checks and an event for every change.
Which transitions are legal is decided by the inbox service (task T4).
"""

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import ConflictError, NotFoundError
from jobs_radar.db.models import InboxEvent, JobInboxItem
from jobs_radar.domain.enums import Actor, InboxAction, InboxState

# Columns a transition may change besides ``state`` and ``version``.
_CHANGEABLE = frozenset(
    {"is_shortlisted", "read_at", "ignore_reason", "note", "applied_at", "application_url"}
)


class InboxRepository:
    """Data access for the owner's inbox."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, owner_id: int, job_inbox_item_id: int) -> JobInboxItem:
        """Return the owner's item; raises ``NotFoundError`` for unknown or foreign ids."""
        item = (
            await self._session.execute(
                select(JobInboxItem).where(
                    JobInboxItem.job_inbox_item_id == job_inbox_item_id,
                    JobInboxItem.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if item is None:
            msg = "Inbox item not found."
            raise NotFoundError(msg)
        return item

    async def surface(self, owner_id: int, job_opportunity_id: int) -> JobInboxItem:
        """Create the owner's item for an opportunity, or return the existing one.

        Creation appends a ``surface_new`` event in the same transaction; a repeated call adds
        nothing. The unique constraint, not a prior lookup, prevents duplicates (LLD section 7).
        """
        inserted_id = (
            await self._session.execute(
                insert(JobInboxItem)
                .values(
                    owner_id=owner_id,
                    job_opportunity_id=job_opportunity_id,
                    state=InboxState.UNREAD.value,
                )
                .on_conflict_do_nothing(index_elements=["owner_id", "job_opportunity_id"])
                .returning(JobInboxItem.job_inbox_item_id)
            )
        ).scalar_one_or_none()
        if inserted_id is None:
            return (
                await self._session.execute(
                    select(JobInboxItem).where(
                        JobInboxItem.owner_id == owner_id,
                        JobInboxItem.job_opportunity_id == job_opportunity_id,
                    )
                )
            ).scalar_one()
        item = await self._session.get(JobInboxItem, inserted_id)
        if item is None:  # cannot happen: the row was inserted in this transaction
            msg = "Inbox item vanished after insert."
            raise RuntimeError(msg)
        self._session.add(
            InboxEvent(
                job_inbox_item_id=item.job_inbox_item_id,
                action=InboxAction.SURFACE_NEW.value,
                actor=Actor.SYSTEM.value,
                from_state=None,
                to_state=InboxState.UNREAD.value,
                metadata_json={},
            )
        )
        await self._session.flush()
        return item

    async def apply(
        self,
        item: JobInboxItem,
        *,
        expected_version: int,
        action: InboxAction,
        to_state: InboxState,
        actor: Actor,
        changes: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> InboxEvent:
        """Change the item and append the matching event atomically.

        Raises:
            ValueError: If ``changes`` names a column that transitions may not change.
            ConflictError: If ``expected_version`` is not the item's current version.
        """
        changes = changes or {}
        forbidden = set(changes) - _CHANGEABLE
        if forbidden:
            msg = f"column not allowed in a transition: {', '.join(sorted(forbidden))}"
            raise ValueError(msg)
        from_state = item.state
        updated = (
            await self._session.execute(
                update(JobInboxItem)
                .where(
                    JobInboxItem.job_inbox_item_id == item.job_inbox_item_id,
                    JobInboxItem.version == expected_version,
                )
                .values(state=to_state.value, version=expected_version + 1, **changes)
                .returning(JobInboxItem.version)
            )
        ).scalar_one_or_none()
        if updated is None:
            await self._session.refresh(item)
            raise ConflictError(
                "The inbox item changed since it was loaded.",
                details={"expected": expected_version, "actual": item.version},
            )
        await self._session.refresh(item)
        event = InboxEvent(
            job_inbox_item_id=item.job_inbox_item_id,
            action=action.value,
            actor=actor.value,
            from_state=from_state,
            to_state=to_state.value,
            metadata_json=metadata or {},
        )
        self._session.add(event)
        await self._session.flush()
        return event
