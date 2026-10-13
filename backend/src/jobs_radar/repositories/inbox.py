"""Inbox items and their append-only event stream (LLD sections 3 and 7; ADR-006).

This layer only offers safe primitives: optimistic version checks, an event for every change and
the read queries behind the inbox list. Which transitions are legal is decided by the inbox
service and the state machine in ``domain.inbox``.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, func, literal, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from jobs_radar.core.errors import ConflictError, NotFoundError
from jobs_radar.db.models import (
    Company,
    CompanyFollow,
    CompanyIgnore,
    InboxEvent,
    IntentRevision,
    JobChangeEvent,
    JobInboxItem,
    JobOpportunity,
    JobOpportunityLink,
    JobPosting,
    JobSnapshot,
    MatchEvaluation,
    ScoreDimension,
    SearchIntent,
    SourceConfiguration,
)
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


SORTS = ("fit_desc", "newest", "oldest")
# Pseudo-state of the "To review" section: unread plus updated-unread items.
TO_REVIEW = "to_review"
_STATES = tuple(state.value for state in InboxState)


@dataclass(frozen=True)
class ListQuery:
    """Everything that narrows and orders the inbox list."""

    owner_id: int
    search_intent_id: int | None
    state: str | None = None
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
    set_aside: bool | None = None
    # Dashboard widget (ADR-065): only offers of followed companies / only recommended ones.
    followed_only: bool = False
    recommended_only: bool = False
    # ADR-060: a recommended job with a fit below this is also set aside; 0 turns the rule off.
    set_aside_below: int = 0


@dataclass(frozen=True)
class RawRow:
    """One inbox list row as read from the database."""

    item: JobInboxItem
    opportunity: JobOpportunity
    company_name: str
    posting: JobPosting
    snapshot: JobSnapshot
    evaluation: MatchEvaluation | None


@dataclass(frozen=True)
class PostingRow:
    """A listing grouped under an opportunity, with its source and link."""

    posting: JobPosting
    source_display_name: str
    link: JobOpportunityLink


class InboxQueries:
    """Read queries for the inbox list, counts and detail."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _select(self, query: ListQuery) -> tuple[Any, Any, Any]:
        snapshot = aliased(JobSnapshot)
        newer_snapshot = aliased(JobSnapshot)
        evaluation = aliased(MatchEvaluation)
        newer_evaluation = aliased(MatchEvaluation)
        latest_snapshot = (
            select(func.max(newer_snapshot.job_snapshot_id))
            .where(newer_snapshot.job_posting_id == JobOpportunity.primary_job_posting_id)
            .scalar_subquery()
        )
        if query.search_intent_id is None:
            on_evaluation: Any = literal(False)
        else:
            latest_evaluation = (
                select(func.max(newer_evaluation.match_evaluation_id))
                .join(
                    IntentRevision,
                    IntentRevision.intent_revision_id == newer_evaluation.intent_revision_id,
                )
                .where(
                    newer_evaluation.job_snapshot_id == snapshot.job_snapshot_id,
                    IntentRevision.search_intent_id == query.search_intent_id,
                )
                .scalar_subquery()
            )
            on_evaluation = evaluation.match_evaluation_id == latest_evaluation
        statement = (
            select(
                JobInboxItem,
                JobOpportunity,
                Company.canonical_name,
                JobPosting,
                snapshot,
                evaluation,
            )
            .select_from(JobInboxItem)
            .join(
                JobOpportunity, JobOpportunity.job_opportunity_id == JobInboxItem.job_opportunity_id
            )
            .join(Company, Company.company_id == JobOpportunity.company_id)
            .join(JobPosting, JobPosting.job_posting_id == JobOpportunity.primary_job_posting_id)
            .join(snapshot, snapshot.job_snapshot_id == latest_snapshot)
            .outerjoin(evaluation, on_evaluation)
            .where(JobInboxItem.owner_id == query.owner_id)
        )
        return statement, evaluation, snapshot

    def _filtered(self, query: ListQuery) -> tuple[Any, Any]:
        statement, evaluation, snapshot = self._select(query)
        if query.state == TO_REVIEW:
            # "To review" holds the unread jobs and those the source changed since (updated).
            statement = statement.where(
                JobInboxItem.state.in_([InboxState.UNREAD.value, InboxState.UPDATED_UNREAD.value])
            )
        elif query.state is not None:
            statement = statement.where(JobInboxItem.state == query.state)
        if query.shortlisted is not None:
            statement = statement.where(JobInboxItem.is_shortlisted.is_(query.shortlisted))
        if query.company:
            statement = statement.where(Company.canonical_name.ilike(f"%{query.company}%"))
        if query.source:
            member = (
                select(JobPosting.job_posting_id)
                .join(
                    JobOpportunityLink,
                    JobOpportunityLink.job_posting_id == JobPosting.job_posting_id,
                )
                .join(
                    SourceConfiguration,
                    SourceConfiguration.source_configuration_id
                    == JobPosting.source_configuration_id,
                )
                .where(
                    JobOpportunityLink.job_opportunity_id == JobOpportunity.job_opportunity_id,
                    JobOpportunityLink.state != "rejected",
                    or_(
                        SourceConfiguration.source_type == query.source,
                        SourceConfiguration.display_name.ilike(f"%{query.source}%"),
                    ),
                )
                .exists()
            )
            statement = statement.where(member)
        if query.text:
            pattern = (
                "%" + query.text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            )
            statement = statement.where(
                or_(
                    Company.canonical_name.ilike(pattern, escape="\\"),
                    snapshot.normalised_json["title"].astext.ilike(pattern, escape="\\"),
                    snapshot.normalised_json["description_text"].astext.ilike(pattern, escape="\\"),
                )
            )
        if query.fit_min is not None:
            statement = statement.where(evaluation.fit_score >= query.fit_min)
        if query.fit_max is not None:
            statement = statement.where(evaluation.fit_score <= query.fit_max)
        if query.evaluated is not None:
            # An outer join leaves the evaluation empty for a job that has no score yet.
            statement = statement.where(
                evaluation.match_evaluation_id.is_not(None)
                if query.evaluated
                else evaluation.match_evaluation_id.is_(None)
            )
        if query.set_aside is not None:
            # Set aside = the latest evaluation for the intent is not recommended (a gate fired,
            # ADR-058) or its fit is below the owner's floor (ADR-060); a job without an
            # evaluation has no verdict yet and is never set aside. A not-recommended job is set
            # aside even when the source changed it (updated-unread); the low-fit floor still
            # leaves updated jobs for the owner to look at.
            is_updated = JobInboxItem.state == InboxState.UPDATED_UNREAD.value
            blocked = or_(
                evaluation.recommendation == "not_recommended",
                and_(~is_updated, evaluation.fit_score < query.set_aside_below),
            )
            statement = statement.where(
                blocked if query.set_aside else ~func.coalesce(blocked, False)
            )
        if query.followed_only:
            followed = (
                select(CompanyFollow.company_follow_id)
                .where(
                    CompanyFollow.owner_id == query.owner_id,
                    CompanyFollow.company_id == JobOpportunity.company_id,
                )
                .exists()
            )
            statement = statement.where(followed)
        if query.recommended_only:
            statement = statement.where(evaluation.recommendation == "recommended")
        if query.first_seen_from is not None:
            statement = statement.where(JobOpportunity.first_seen_at >= query.first_seen_from)
        if query.first_seen_to is not None:
            statement = statement.where(JobOpportunity.first_seen_at <= query.first_seen_to)
        if not query.include_closed:
            statement = statement.where(
                or_(
                    JobOpportunity.closed_at.is_(None),
                    JobInboxItem.state == InboxState.APPLIED.value,
                )
            )
        return statement, evaluation

    async def page(
        self, query: ListQuery, *, limit: int, after: tuple[int, datetime, int] | None
    ) -> list[RawRow]:
        """Return up to ``limit`` rows after the keyset position ``after``.

        The key is ``(fit, first seen, item id)``; for the date sorts the fit part is constant.
        """
        statement, evaluation = self._filtered(query)
        fit = func.coalesce(evaluation.fit_score, -1)
        seen, item_id = JobOpportunity.first_seen_at, JobInboxItem.job_inbox_item_id
        order: tuple[Any, ...]
        if query.sort == "fit_desc":
            order = (fit.desc(), seen.desc(), item_id.desc())
            key = tuple_(fit, seen, item_id)
            descending = True
        elif query.sort == "newest":
            order = (seen.desc(), item_id.desc())
            key = tuple_(literal(0), seen, item_id)
            descending = True
        else:
            order = (seen.asc(), item_id.asc())
            key = tuple_(literal(0), seen, item_id)
            descending = False
        if after is not None:
            position = tuple_(literal(after[0]), literal(after[1]), literal(after[2]))
            statement = statement.where(key < position if descending else key > position)
        rows = (await self._session.execute(statement.order_by(*order).limit(limit))).all()
        return [
            RawRow(item, opportunity, company, posting, snapshot, ev)
            for item, opportunity, company, posting, snapshot, ev in rows
        ]

    async def count(self, query: ListQuery) -> int:
        """Return how many items match ``query`` (same filters as the list, without paging)."""
        statement, _evaluation = self._filtered(query)
        return (
            await self._session.execute(select(func.count()).select_from(statement.subquery()))
        ).scalar_one()

    async def counts(
        self,
        owner_id: int,
        *,
        include_closed: bool,
        search_intent_id: int | None = None,
        set_aside_below: int = 0,
    ) -> dict[str, int]:
        """Return the number of items per state, the shortlisted ones and the total.

        Unread and updated-unread jobs that the intent's latest evaluation does not recommend
        are counted as ``set_aside`` instead (ADR-058); the total still holds every item.
        """
        shortlisted_flag = case((JobInboxItem.is_shortlisted.is_(True), 1), else_=0)
        statement = (
            select(JobInboxItem.state, func.count(), func.sum(shortlisted_flag))
            .join(
                JobOpportunity, JobOpportunity.job_opportunity_id == JobInboxItem.job_opportunity_id
            )
            .where(JobInboxItem.owner_id == owner_id)
            .group_by(JobInboxItem.state)
        )
        if not include_closed:
            statement = statement.where(
                or_(
                    JobOpportunity.closed_at.is_(None),
                    JobInboxItem.state == InboxState.APPLIED.value,
                )
            )
        counts = dict.fromkeys(_STATES, 0)
        shortlisted = 0
        for state, number, flagged in (await self._session.execute(statement)).all():
            counts[state] = int(number)
            shortlisted += int(flagged or 0)
        total = sum(counts.values())
        set_aside = 0
        for state in (InboxState.UNREAD.value, InboxState.UPDATED_UNREAD.value):
            aside_query = ListQuery(
                owner_id=owner_id,
                search_intent_id=search_intent_id,
                state=state,
                include_closed=include_closed,
                set_aside=True,
                set_aside_below=set_aside_below,
            )
            aside_statement, _evaluation = self._filtered(aside_query)
            aside = (
                await self._session.execute(
                    select(func.count()).select_from(aside_statement.subquery())
                )
            ).scalar_one()
            counts[state] -= aside
            set_aside += aside
        return {**counts, "set_aside": set_aside, "shortlisted": shortlisted, "total": total}

    async def dimensions(self, evaluation_ids: list[int]) -> dict[int, list[ScoreDimension]]:
        """Return the dimensions of each evaluation."""
        if not evaluation_ids:
            return {}
        rows = await self._session.execute(
            select(ScoreDimension)
            .where(ScoreDimension.match_evaluation_id.in_(evaluation_ids))
            .order_by(ScoreDimension.score_dimension_id)
        )
        grouped: dict[int, list[ScoreDimension]] = {i: [] for i in evaluation_ids}
        for row in rows.scalars():
            grouped[row.match_evaluation_id].append(row)
        return grouped

    async def postings(self, opportunity_ids: list[int]) -> dict[int, list[PostingRow]]:
        """Return the listings grouped under each opportunity."""
        if not opportunity_ids:
            return {}
        rows = await self._session.execute(
            select(JobOpportunityLink, JobPosting, SourceConfiguration.display_name)
            .join(JobPosting, JobPosting.job_posting_id == JobOpportunityLink.job_posting_id)
            .join(
                SourceConfiguration,
                SourceConfiguration.source_configuration_id == JobPosting.source_configuration_id,
            )
            .where(
                JobOpportunityLink.job_opportunity_id.in_(opportunity_ids),
                JobOpportunityLink.state != "rejected",
            )
            .order_by(JobPosting.job_posting_id)
        )
        grouped: dict[int, list[PostingRow]] = {i: [] for i in opportunity_ids}
        for link, posting, display_name in rows.all():
            grouped[link.job_opportunity_id].append(PostingRow(posting, display_name, link))
        return grouped

    async def one(self, query: ListQuery, job_inbox_item_id: int) -> RawRow | None:
        """Return one row (same shape as the list) for an item, if it exists."""
        statement, _evaluation, _snapshot = self._select(query)
        statement = statement.where(JobInboxItem.job_inbox_item_id == job_inbox_item_id)
        row = (await self._session.execute(statement)).first()
        if row is None:
            return None
        item, opportunity, company, posting, snapshot, ev = row
        return RawRow(item, opportunity, company, posting, snapshot, ev)

    async def events(self, job_inbox_item_id: int, limit: int) -> list[InboxEvent]:
        """Return the item's newest events first."""
        rows = await self._session.execute(
            select(InboxEvent)
            .where(InboxEvent.job_inbox_item_id == job_inbox_item_id)
            .order_by(InboxEvent.inbox_event_id.desc())
            .limit(limit)
        )
        return list(rows.scalars())

    async def latest_change(self, job_posting_id: int) -> JobChangeEvent | None:
        """Return the posting's latest material change, if any."""
        return (
            await self._session.execute(
                select(JobChangeEvent)
                .where(JobChangeEvent.job_posting_id == job_posting_id)
                .order_by(JobChangeEvent.job_change_event_id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def default_intent_id(self, owner_id: int) -> int | None:
        """Return the owner's first enabled intent (used when none is chosen)."""
        return (
            await self._session.execute(
                select(SearchIntent.search_intent_id)
                .where(SearchIntent.owner_id == owner_id, SearchIntent.enabled.is_(True))
                .order_by(SearchIntent.search_intent_id)
                .limit(1)
            )
        ).scalar_one_or_none()

    async def unsurfaced(self, owner_id: int, limit: int) -> list[int]:
        """Return open opportunities that have no inbox item for the owner yet."""
        has_item = (
            select(JobInboxItem.job_inbox_item_id)
            .where(
                JobInboxItem.owner_id == owner_id,
                JobInboxItem.job_opportunity_id == JobOpportunity.job_opportunity_id,
            )
            .exists()
        )
        rows = await self._session.execute(
            select(JobOpportunity.job_opportunity_id)
            .where(JobOpportunity.closed_at.is_(None), ~has_item)
            .order_by(JobOpportunity.first_seen_at.desc(), JobOpportunity.job_opportunity_id.desc())
            .limit(limit)
        )
        return [int(i) for i in rows.scalars()]

    async def company_is_ignored(self, owner_id: int, job_opportunity_id: int) -> bool:
        """Whether the owner ignores the company of the opportunity (ADR-061)."""
        found = await self._session.execute(
            select(CompanyIgnore.company_ignore_id)
            .join(JobOpportunity, JobOpportunity.company_id == CompanyIgnore.company_id)
            .where(
                CompanyIgnore.owner_id == owner_id,
                JobOpportunity.job_opportunity_id == job_opportunity_id,
            )
        )
        return found.first() is not None

    async def company_items(
        self, owner_id: int, company_id: int, *, states: list[InboxState], reason: str | None = None
    ) -> list[JobInboxItem]:
        """Items of the company's opportunities in the given states (and ignore reason)."""
        statement = (
            select(JobInboxItem)
            .join(
                JobOpportunity,
                JobOpportunity.job_opportunity_id == JobInboxItem.job_opportunity_id,
            )
            .where(
                JobInboxItem.owner_id == owner_id,
                JobOpportunity.company_id == company_id,
                JobInboxItem.state.in_([state.value for state in states]),
            )
        )
        if reason is not None:
            statement = statement.where(JobInboxItem.ignore_reason == reason)
        return list((await self._session.execute(statement)).scalars())

    async def company_unsurfaced(self, owner_id: int, company_id: int) -> list[int]:
        """Open opportunities of the company that have no inbox item for the owner yet."""
        has_item = (
            select(JobInboxItem.job_inbox_item_id)
            .where(
                JobInboxItem.owner_id == owner_id,
                JobInboxItem.job_opportunity_id == JobOpportunity.job_opportunity_id,
            )
            .exists()
        )
        rows = await self._session.execute(
            select(JobOpportunity.job_opportunity_id).where(
                JobOpportunity.company_id == company_id,
                JobOpportunity.closed_at.is_(None),
                ~has_item,
            )
        )
        return [int(i) for i in rows.scalars()]

    async def items_for_posting(self, job_posting_id: int) -> list[JobInboxItem]:
        """Return the inbox items of the opportunity the posting is grouped under."""
        rows = await self._session.execute(
            select(JobInboxItem)
            .join(
                JobOpportunityLink,
                JobOpportunityLink.job_opportunity_id == JobInboxItem.job_opportunity_id,
            )
            .where(
                JobOpportunityLink.job_posting_id == job_posting_id,
                JobOpportunityLink.state != "rejected",
            )
        )
        return list(rows.scalars())
