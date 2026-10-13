"""Inbox use cases: surfacing opportunities, actions, the list and the detail (T4.8).

The inbox is keyed by opportunity (ADR-023, decision D7). Every state change goes through the
state machine in ``domain.inbox``, checks the version the owner saw and appends an event in the
same transaction. A job without a score is listed as "not evaluated"; nothing is hidden because AI
is off. Scores shown are the latest evaluation of the primary listing's latest snapshot under the
chosen intent.
"""

import base64
import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import InputValidationError, NotFoundError
from jobs_radar.db.models import (
    InboxEvent,
    JobChangeEvent,
    JobInboxItem,
    MatchEvaluation,
    ScoreDimension,
)
from jobs_radar.domain.enums import Actor, InboxAction, InboxState
from jobs_radar.domain.inbox import InvalidTransitionError, next_state
from jobs_radar.repositories.inbox import (
    SORTS,
    InboxQueries,
    InboxRepository,
    ListQuery,
    PostingRow,
    RawRow,
)
from jobs_radar.repositories.schedule import ScheduleRepository
from jobs_radar.services.job_brief import JobBrief, JobBriefService

_USER_ACTIONS = frozenset(InboxAction) - {InboxAction.SURFACE_NEW, InboxAction.MATERIAL_UPDATE}
_EVENT_LIMIT = 25
_SURFACE_BATCH = 1000

# Reason code on items ignored because the owner ignores their company (ADR-061).
COMPANY_IGNORED_REASON = "company_ignored"


@dataclass(frozen=True)
class InboxFilters:
    """What the owner narrowed the list to. ``state=None`` means every state."""

    search_intent_id: int | None = None
    state: str | None = "unread"
    shortlisted: bool | None = None
    company: str | None = None
    source: str | None = None
    text: str | None = None
    fit_min: int | None = None
    fit_max: int | None = None
    evaluated: bool | None = None
    first_seen_from: datetime | None = None
    first_seen_to: datetime | None = None
    include_closed: bool = False
    sort: str = "fit_desc"
    set_aside: bool | None = None  # ADR-058: True only the set-aside jobs, False without them


@dataclass(frozen=True)
class InboxRowView:
    """A row of the inbox list."""

    item: JobInboxItem
    title: str
    company_name: str
    locations: list[str]
    first_seen_at: datetime
    last_seen_at: datetime
    closed_at: datetime | None
    evaluation: MatchEvaluation | None
    dimensions: list[ScoreDimension]
    postings: list[PostingRow]
    job_opportunity_id: int
    job_posting_id: int


@dataclass(frozen=True)
class InboxPage:
    """A page of the list with the cursor for the next one and the counts for the tabs."""

    rows: list[InboxRowView]
    next_cursor: str | None
    counts: dict[str, int]
    search_intent_id: int | None
    set_aside_below_fit: int


@dataclass(frozen=True)
class WidgetSummary:
    """What a dashboard widget shows: jobs waiting for review and the best fit among them."""

    to_review: int
    to_review_high_fit: int
    best_fit: int | None
    followed_recommended: int


@dataclass(frozen=True)
class InboxDetail:
    """One item with everything the detail panel shows."""

    row: InboxRowView
    description: str
    apply_url: str | None
    dimensions: list[ScoreDimension]
    postings: list[PostingRow]
    events: list[InboxEvent]
    last_change: JobChangeEvent | None
    note: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    brief: JobBrief = field(default_factory=JobBrief)


@dataclass(frozen=True)
class ActionResult:
    """The item after an action and the event it appended (``None`` when nothing changed)."""

    item: JobInboxItem
    event: InboxEvent | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _encode_cursor(sort: str, fit: int, seen: datetime, item_id: int) -> str:
    raw = json.dumps({"s": sort, "f": fit, "t": seen.isoformat(), "i": item_id})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str, sort: str) -> tuple[int, datetime, int]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if data["s"] != sort:
            msg = "The cursor belongs to a different sort order."
            raise ValueError(msg)
        return int(data["f"]), datetime.fromisoformat(data["t"]), int(data["i"])
    except (ValueError, KeyError, TypeError) as exc:
        msg = "The cursor is not valid."
        raise InputValidationError(msg) from exc


class InboxService:
    """Use cases around the owner's inbox. The caller owns the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._items = InboxRepository(session)
        self._queries = InboxQueries(session)
        self._schedule = ScheduleRepository(session)

    # --- surfacing and system events -----------------------------------------

    async def surface_new(self, owner_id: int) -> int:
        """Create an item (and its ``surface_new`` event) for each opportunity that has none."""
        created = 0
        for opportunity_id in await self._queries.unsurfaced(owner_id, _SURFACE_BATCH):
            item = await self._items.surface(owner_id, opportunity_id)
            if await self._queries.company_is_ignored(owner_id, opportunity_id):
                await self._ignore_for_company(item)  # never shown as unread (ADR-061)
            created += 1
        return created

    async def _ignore_for_company(self, item: JobInboxItem) -> None:
        """Move an item to ignored because its company is ignored."""
        await self._items.apply(
            item,
            expected_version=item.version,
            action=InboxAction.IGNORE,
            to_state=InboxState.IGNORED,
            actor=Actor.SYSTEM,
            changes={"ignore_reason": COMPANY_IGNORED_REASON},
            metadata={"reason": COMPANY_IGNORED_REASON},
        )

    async def ignore_company(self, owner_id: int, company_id: int) -> int:
        """Ignore every open offer of the company at once; returns how many items moved.

        Archived, applied and already ignored items are left alone (ADR-061).
        """
        for opportunity_id in await self._queries.company_unsurfaced(owner_id, company_id):
            await self._items.surface(owner_id, opportunity_id)
        items = await self._queries.company_items(
            owner_id,
            company_id,
            states=[InboxState.UNREAD, InboxState.READ, InboxState.UPDATED_UNREAD],
        )
        for item in items:
            await self._ignore_for_company(item)
        return len(items)

    async def restore_company(self, owner_id: int, company_id: int) -> int:
        """Restore only the items the company ignore moved; returns how many came back."""
        items = await self._queries.company_items(
            owner_id,
            company_id,
            states=[InboxState.IGNORED],
            reason=COMPANY_IGNORED_REASON,
        )
        for item in items:
            await self._items.apply(
                item,
                expected_version=item.version,
                action=InboxAction.RESTORE,
                to_state=InboxState.READ,
                actor=Actor.SYSTEM,
                changes={"ignore_reason": None},
            )
        return len(items)

    async def notify_material_change(self, job_posting_id: int) -> int:
        """Move eligible items of the posting's opportunity to ``updated_unread``.

        Ignored, archived and applied items never change automatically, and an item that is
        already ``updated_unread`` has nothing to record. Returns how many items were moved.
        """
        moved = 0
        for item in await self._queries.items_for_posting(job_posting_id):
            try:
                target = next_state(InboxState(item.state), InboxAction.MATERIAL_UPDATE)
            except InvalidTransitionError:
                continue
            if target.value == item.state:
                continue
            await self._items.apply(
                item,
                expected_version=item.version,
                action=InboxAction.MATERIAL_UPDATE,
                to_state=target,
                actor=Actor.SYSTEM,
            )
            moved += 1
        return moved

    # --- actions -------------------------------------------------------------

    async def act(
        self,
        owner_id: int,
        job_inbox_item_id: int,
        action: InboxAction,
        *,
        expected_version: int,
        reason: str | None = None,
        note: str | None = None,
        applied_at: datetime | None = None,
        application_url: str | None = None,
    ) -> ActionResult:
        """Perform one owner action on an item.

        Raises:
            NotFoundError: unknown or foreign item.
            InputValidationError: the action is not allowed from the item's state.
            ConflictError: ``expected_version`` is not the item's current version.
        """
        item = await self._items.get(owner_id, job_inbox_item_id)
        if action not in _USER_ACTIONS:
            msg = f"'{action.value}' is not an action the owner can take."
            raise InputValidationError(msg)
        state = InboxState(item.state)
        if action is InboxAction.OPEN and state is InboxState.READ:
            return ActionResult(item, None)  # opening again is harmless: nothing to record
        try:
            target = next_state(state, action)
        except InvalidTransitionError as error:
            raise InputValidationError(str(error)) from error

        changes: dict[str, Any] = {}
        metadata: dict[str, Any] = {}
        if action is InboxAction.SHORTLIST:
            if item.is_shortlisted:
                msg = "This item is already shortlisted."
                raise InputValidationError(msg)
            changes["is_shortlisted"] = True
        elif action is InboxAction.UNSHORTLIST:
            if not item.is_shortlisted:
                msg = "This item is not shortlisted."
                raise InputValidationError(msg)
            changes["is_shortlisted"] = False
        elif action is InboxAction.OPEN:
            changes["read_at"] = item.read_at or _utc_now()
        elif action is InboxAction.IGNORE:
            changes.update(ignore_reason=reason, note=note if note is not None else item.note)
            if reason:
                metadata["reason"] = reason  # events carry codes, never free text
        elif action is InboxAction.RECORD_APPLICATION:
            moment = applied_at or _utc_now()
            changes.update(
                applied_at=moment,
                application_url=application_url,
                note=note if note is not None else item.note,
            )
            metadata["applied_at"] = moment.isoformat()
        elif action is InboxAction.RESTORE and state is InboxState.APPLIED:
            changes.update(applied_at=None, application_url=None)
        if action is InboxAction.RESTORE:
            changes.setdefault("ignore_reason", None)

        event = await self._items.apply(
            item,
            expected_version=expected_version,
            action=action,
            to_state=target,
            actor=Actor.USER,
            changes=changes,
            metadata=metadata,
        )
        return ActionResult(item, event)

    # --- reading -------------------------------------------------------------

    async def _intent(self, owner_id: int, requested: int | None) -> int | None:
        return (
            requested if requested is not None else await self._queries.default_intent_id(owner_id)
        )

    def _query(
        self, owner_id: int, intent_id: int | None, filters: InboxFilters, floor: int
    ) -> ListQuery:
        if filters.sort not in SORTS:
            msg = f"Unknown sort '{filters.sort}'. Use one of: {', '.join(SORTS)}."
            raise InputValidationError(msg)
        return ListQuery(
            owner_id=owner_id,
            search_intent_id=intent_id,
            state=None if filters.state in (None, "all") else filters.state,
            shortlisted=filters.shortlisted,
            company=filters.company,
            source=filters.source,
            text=filters.text,
            fit_min=filters.fit_min,
            fit_max=filters.fit_max,
            evaluated=filters.evaluated,
            first_seen_from=filters.first_seen_from,
            first_seen_to=filters.first_seen_to,
            include_closed=filters.include_closed,
            sort=filters.sort,
            set_aside=filters.set_aside,
            set_aside_below=floor,
        )

    async def _views(self, rows: list[RawRow]) -> list[InboxRowView]:
        evaluation_ids = [r.evaluation.match_evaluation_id for r in rows if r.evaluation]
        dimensions = await self._queries.dimensions(evaluation_ids)
        postings = await self._queries.postings([r.opportunity.job_opportunity_id for r in rows])
        views: list[InboxRowView] = []
        for row in rows:
            normalised: dict[str, Any] = row.snapshot.normalised_json
            locations = [
                loc["raw"]
                for loc in normalised.get("work_arrangement", {}).get("locations", [])
                if loc.get("raw")
            ]
            views.append(
                InboxRowView(
                    item=row.item,
                    title=normalised["title"],
                    company_name=row.company_name,
                    locations=locations,
                    first_seen_at=row.opportunity.first_seen_at,
                    last_seen_at=row.opportunity.last_seen_at,
                    closed_at=row.opportunity.closed_at,
                    evaluation=row.evaluation,
                    dimensions=dimensions.get(row.evaluation.match_evaluation_id, [])
                    if row.evaluation
                    else [],
                    postings=postings.get(row.opportunity.job_opportunity_id, []),
                    job_opportunity_id=row.opportunity.job_opportunity_id,
                    job_posting_id=row.posting.job_posting_id,
                )
            )
        return views

    async def widget_summary(
        self, owner_id: int, fit_min: int, search_intent_id: int | None = None
    ) -> WidgetSummary:
        """Count the offers waiting for review, as the sidebar badge does, and those at fit_min+.

        Waiting for review = unread (set-aside offers left out) plus updated-unread.
        """
        intent_id = await self._intent(owner_id, search_intent_id)
        floor = await self._schedule.set_aside_below_fit(owner_id)

        def query(state: str, minimum: int | None = None) -> ListQuery:
            # Like the sidebar badge: set-aside jobs leave "unread" (ADR-058/060), while every
            # updated-unread job still waits for the owner.
            return self._query(
                owner_id,
                intent_id,
                InboxFilters(
                    state=state, set_aside=False if state == "unread" else None, fit_min=minimum
                ),
                floor,
            )

        states = ("unread", "updated_unread")
        to_review = sum([await self._queries.count(query(st)) for st in states])
        high = sum([await self._queries.count(query(st, fit_min)) for st in states])
        followed = sum(
            [
                await self._queries.count(
                    replace(query(st), followed_only=True, recommended_only=True)
                )
                for st in states
            ]
        )
        # The best fit among all of them: the top row of each state, then the larger one.
        tops = [await self._queries.page(query(st), limit=1, after=None) for st in states]
        fits = [r[0].evaluation.fit_score for r in tops if r and r[0].evaluation]
        return WidgetSummary(to_review, high, max(fits, default=None), followed)

    async def list_items(
        self,
        owner_id: int,
        filters: InboxFilters,
        *,
        limit: int,
        cursor: str | None = None,
    ) -> InboxPage:
        """Return one page of the inbox, the cursor for the next page and the tab counts.

        Raises:
            InputValidationError: unknown sort or a cursor that is not valid for this sort.
        """
        intent_id = await self._intent(owner_id, filters.search_intent_id)
        floor = await self._schedule.set_aside_below_fit(owner_id)
        query = self._query(owner_id, intent_id, filters, floor)
        after = _decode_cursor(cursor, query.sort) if cursor else None
        rows = await self._queries.page(query, limit=limit + 1, after=after)
        more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if more and rows:
            last = rows[-1]
            fit = last.evaluation.fit_score if last.evaluation else -1
            next_cursor = _encode_cursor(
                query.sort,
                fit if query.sort == "fit_desc" else 0,
                last.opportunity.first_seen_at,
                last.item.job_inbox_item_id,
            )
        counts = await self._queries.counts(
            owner_id,
            include_closed=filters.include_closed,
            search_intent_id=intent_id,
            set_aside_below=floor,
        )
        return InboxPage(await self._views(rows), next_cursor, counts, intent_id, floor)

    async def detail(
        self, owner_id: int, job_inbox_item_id: int, *, search_intent_id: int | None = None
    ) -> InboxDetail:
        """Return one item with its job text, sites, score, evidence and history.

        Raises:
            NotFoundError: unknown or foreign item.
        """
        intent_id = await self._intent(owner_id, search_intent_id)
        query = ListQuery(owner_id=owner_id, search_intent_id=intent_id, include_closed=True)
        row = await self._queries.one(query, job_inbox_item_id)
        if row is None:
            msg = "Inbox item not found."
            raise NotFoundError(msg)
        (view,) = await self._views([row])
        normalised: dict[str, Any] = row.snapshot.normalised_json
        source = normalised.get("source", {})
        return InboxDetail(
            row=view,
            description=normalised.get("description_text", ""),
            apply_url=source.get("apply_url") or source.get("url"),
            dimensions=view.dimensions,
            postings=view.postings,
            events=await self._queries.events(job_inbox_item_id, _EVENT_LIMIT),
            last_change=await self._queries.latest_change(row.posting.job_posting_id),
            note=row.item.note,
            brief=await JobBriefService(self._session).for_posting(row.posting.job_posting_id),
        )


class InboxRunner:
    """Creates inbox items for new opportunities in its own transaction (used by the worker)."""

    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        owner_id: int,
    ) -> None:
        self._session_factory = session_factory
        self._owner_id = owner_id

    async def run(self) -> int:
        """Surface opportunities that have no inbox item yet; return how many were created."""
        async with self._session_factory() as session:
            created = await InboxService(session).surface_new(self._owner_id)
            await session.commit()
            return created
