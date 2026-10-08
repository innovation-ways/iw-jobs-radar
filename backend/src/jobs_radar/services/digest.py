"""The daily digest (T5.4): what is worth looking at today. In-app only (ADR-017).

Three sections: new opportunities at or above the intent's alert threshold, shortlisted jobs whose
posting changed materially, and sources needing attention (failed last run, no success for two
days, or never run). Scores come from the same evaluations as the inbox.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import CollectionRun, IntentRevision, SearchIntent
from jobs_radar.domain.enums import RunStatus
from jobs_radar.repositories.inbox import InboxQueries
from jobs_radar.services.inbox import InboxFilters, InboxRowView, InboxService
from jobs_radar.services.sources import SourceService

Clock = Callable[[], datetime]

DEFAULT_ALERT_THRESHOLD = 65
WINDOW = timedelta(hours=24)
# An enabled source with no successful run for this long needs attention.
STALE_AFTER = timedelta(hours=48)
_SECTION_LIMIT = 20
_CANDIDATES = 100
_REVIEWABLE = {"unread", "read", "updated_unread"}


@dataclass(frozen=True)
class ChangedItem:
    """A shortlisted job whose posting changed materially in the window."""

    row: InboxRowView
    changed_fields: list[str]
    changed_at: datetime


@dataclass(frozen=True)
class SourceHealth:
    """An enabled source that needs the owner's attention."""

    source_configuration_id: int
    display_name: str
    status: str  # failed | stale | never_run
    error_class: str | None
    error_message: str | None
    last_run_at: datetime | None


@dataclass(frozen=True)
class Digest:
    """The digest of one day."""

    generated_at: datetime
    since: datetime
    search_intent_id: int | None
    alert_threshold: int
    new_high_fit: list[InboxRowView]
    changed_shortlisted: list[ChangedItem]
    source_health: list[SourceHealth]
    last_run: CollectionRun | None
    counts: dict[str, int]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DigestService:
    """Builds the daily digest. The caller owns the transaction."""

    def __init__(self, session: AsyncSession, *, clock: Clock = _utc_now) -> None:
        self._session = session
        self._clock = clock
        self._inbox = InboxService(session)
        self._queries = InboxQueries(session)

    async def _threshold(self, intent_id: int | None) -> int:
        if intent_id is None:
            return DEFAULT_ALERT_THRESHOLD
        definition: Any = (
            await self._session.execute(
                select(IntentRevision.intent_json)
                .join(
                    SearchIntent,
                    SearchIntent.current_intent_revision_id == IntentRevision.intent_revision_id,
                )
                .where(SearchIntent.search_intent_id == intent_id)
            )
        ).scalar_one_or_none()
        if definition is None:
            msg = f"Search intent {intent_id} does not exist or has no revision."
            raise NotFoundError(msg)
        return int(definition["alert_threshold"])

    async def build(self, owner_id: int, *, search_intent_id: int | None = None) -> Digest:
        """Build the digest for the last 24 hours, scored under ``search_intent_id``."""
        now = self._clock()
        since = now - WINDOW
        intent_id = (
            search_intent_id
            if search_intent_id is not None
            else await self._queries.default_intent_id(owner_id)
        )
        threshold = await self._threshold(intent_id)

        fresh = await self._inbox.list_items(
            owner_id,
            InboxFilters(
                search_intent_id=intent_id,
                state=None,
                fit_min=threshold,
                first_seen_from=since,
                sort="fit_desc",
            ),
            limit=_CANDIDATES,
        )
        new_high_fit = [
            row
            for row in fresh.rows
            if row.item.state in _REVIEWABLE
            and row.evaluation is not None
            and row.evaluation.recommendation == "recommended"
        ][:_SECTION_LIMIT]

        starred = await self._inbox.list_items(
            owner_id,
            InboxFilters(search_intent_id=intent_id, state=None, shortlisted=True, sort="newest"),
            limit=_CANDIDATES,
        )
        changed: list[ChangedItem] = []
        for row in starred.rows:
            if row.item.state == "ignored":
                continue
            change = await self._queries.latest_change(row.job_posting_id)
            if change is not None and change.created_at >= since:
                changed.append(ChangedItem(row, list(change.changed_fields), change.created_at))
        changed.sort(key=lambda c: c.changed_at, reverse=True)

        health = await self._source_health(owner_id, now)
        last_run = (
            await self._session.execute(
                select(CollectionRun)
                .where(
                    CollectionRun.owner_id == owner_id,
                    CollectionRun.status.in_(
                        (RunStatus.SUCCEEDED.value, RunStatus.PARTIAL.value, RunStatus.FAILED.value)
                    ),
                )
                .order_by(CollectionRun.collection_run_id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return Digest(
            generated_at=now,
            since=since,
            search_intent_id=intent_id,
            alert_threshold=threshold,
            new_high_fit=new_high_fit,
            changed_shortlisted=changed[:_SECTION_LIMIT],
            source_health=health,
            last_run=last_run,
            counts={
                "new_high_fit": len(new_high_fit),
                "changed_shortlisted": len(changed),
                "sources_needing_attention": len(health),
            },
        )

    async def _source_health(self, owner_id: int, now: datetime) -> list[SourceHealth]:
        needing: list[SourceHealth] = []
        for row in await SourceService(self._session, {}).list_with_status(owner_id):
            source, result = row.source, row.last_result
            if not source.enabled:
                continue
            base = (source.source_configuration_id, source.display_name)
            if result is None:
                needing.append(SourceHealth(*base, "never_run", None, None, None))
            elif result.outcome == "failed":
                needing.append(
                    SourceHealth(
                        *base,
                        "failed",
                        result.error_class,
                        result.error_message,
                        result.finished_at,
                    )
                )
            elif now - result.finished_at > STALE_AFTER:
                needing.append(SourceHealth(*base, "stale", None, None, result.finished_at))
        return needing
