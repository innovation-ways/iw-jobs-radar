"""Weekly market trends of the jobs that are relevant to an intent (T7.5, T7.6, ADR-022).

*Relevant* means the latest evaluation of the opportunity under the intent has a fit at or above
the threshold (default 45) and is not ``not_recommended``. For every week and term the job stores
open, new and closed counts plus the relevant total, so the screen can show **shares** (counts rise
when sources are added), mark weeks where the **intent revision** or the **source set** changed,
and only offer the history that exists. Terms of the taxonomy are followed through ``replaced_by``
so a merged term stays one continuous line. Each run backfills once, then recomputes the last two
weeks (under the current intent revision); older weeks keep the revision they were computed under.
"""

from collections import defaultdict
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import (
    IntentRevision,
    JobExtraction,
    JobOpportunity,
    JobSnapshot,
    MatchEvaluation,
    SearchIntent,
    Skill,
    SourceConfiguration,
    TaxonomyTerm,
    TaxonomyVersion,
    TrendWeekly,
)
from jobs_radar.domain.enums import Recommendation, TrendTermKind
from jobs_radar.domain.trends import (
    Period,
    change_between,
    change_points,
    is_open_at,
    period_availability,
    share,
    source_set_hash,
    week_range,
    week_start,
)
from jobs_radar.services.evaluation_inputs import job_attributes

Clock = Callable[[], datetime]
DEFAULT_RELEVANCE_MIN_SCORE = 45
RECOMPUTED_WEEKS = 2
_TAXONOMY_KINDS = {
    TrendTermKind.ROLE_FAMILY: "role_family",
    TrendTermKind.SECTOR: "sector",
    TrendTermKind.WORK_ARRANGEMENT: "work_arrangement",
    TrendTermKind.SENIORITY_LEVEL: "seniority_level",
    TrendTermKind.ENGAGEMENT_TYPE: "engagement_type",
}


@dataclass(frozen=True)
class SeriesPoint:
    """One week of one term."""

    week_start: date
    open_count: int
    share: float | None


@dataclass(frozen=True)
class TrendRow:
    """A ranked term with its weekly series."""

    term_key: str
    label: str
    open_now: int
    share_now: float | None
    share_change: float | None
    count_change: int
    series: list[SeriesPoint]


@dataclass(frozen=True)
class WeekMeta:
    """Facts about a week that explain why it may not be comparable."""

    week_start: date
    relevant_total_open: int
    intent_revision_id: int | None
    source_set_hash: str | None


@dataclass(frozen=True)
class TrendReport:
    """The Trends screen data for one term kind."""

    kind: str
    search_intent_id: int
    relevance_min_score: int
    available_weeks: int
    first_week: date | None
    periods: list[Period]
    weeks: list[WeekMeta]
    rows: list[TrendRow]
    intent_revision_changes: list[date]
    source_set_changes: list[date]


@dataclass(frozen=True)
class _Opportunity:
    first_seen: datetime
    closed: datetime | None
    terms: dict[str, set[str]]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def terms_of(attributes: dict[str, Any]) -> dict[str, set[str]]:
    """Return the trend terms of a stored extraction, by term kind."""
    job = job_attributes(attributes, "", "", "")
    terms: dict[str, set[str]] = defaultdict(set)
    for key, _confidence in job.role_families:
        terms[TrendTermKind.ROLE_FAMILY.value].add(key)
    if job.sector_primary:
        terms[TrendTermKind.SECTOR.value].add(job.sector_primary)
    if job.work_mode:
        terms[TrendTermKind.WORK_ARRANGEMENT.value].add(job.work_mode)
    for level in job.seniority_levels or ():
        terms[TrendTermKind.SENIORITY_LEVEL.value].add(level)
    for kind in job.employment_types or ():
        terms[TrendTermKind.ENGAGEMENT_TYPE.value].add(kind)
    for skill in job.skills:
        terms[TrendTermKind.SKILL.value].add(str(skill.skill_id))
    return dict(terms)


class TrendService:
    """Computes and reports trends. The caller owns the transaction."""

    def __init__(self, session: AsyncSession, *, clock: Clock = _utc_now) -> None:
        self._session = session
        self._clock = clock

    # --- loading -------------------------------------------------------------------------------

    async def _intent(self, owner_id: int, search_intent_id: int) -> SearchIntent:
        intent = (
            await self._session.execute(
                select(SearchIntent).where(
                    SearchIntent.owner_id == owner_id,
                    SearchIntent.search_intent_id == search_intent_id,
                )
            )
        ).scalar_one_or_none()
        if intent is None:
            msg = f"Search intent {search_intent_id} does not exist."
            raise NotFoundError(msg)
        return intent

    async def _replacements(self) -> dict[tuple[str, str], str]:
        """Map retired taxonomy terms to the term that replaced them (followed to the end)."""
        rows = (await self._session.execute(select(TaxonomyTerm))).scalars().all()
        by_id = {t.taxonomy_term_id: t for t in rows}
        result: dict[tuple[str, str], str] = {}
        for term in rows:
            current, hops = term, 0
            while current.replaced_by_taxonomy_term_id is not None and hops < 10:
                current = by_id[current.replaced_by_taxonomy_term_id]
                hops += 1
            if current is not term:
                result[(term.kind, term.term_key)] = current.term_key
        return result

    async def _relevant(self, search_intent_id: int, minimum: int) -> list[_Opportunity]:
        evaluation = aliased(MatchEvaluation)
        newer_snapshot = aliased(JobSnapshot)
        newer_evaluation = aliased(MatchEvaluation)
        latest_snapshot = (
            select(func.max(newer_snapshot.job_snapshot_id))
            .where(newer_snapshot.job_posting_id == JobOpportunity.primary_job_posting_id)
            .correlate(JobOpportunity)
            .scalar_subquery()
        )
        latest_evaluation = (
            select(func.max(newer_evaluation.match_evaluation_id))
            .join(
                IntentRevision,
                IntentRevision.intent_revision_id == newer_evaluation.intent_revision_id,
            )
            .where(
                newer_evaluation.job_snapshot_id == latest_snapshot,
                IntentRevision.search_intent_id == search_intent_id,
            )
            .correlate(JobOpportunity)
            .scalar_subquery()
        )
        rows = await self._session.execute(
            select(
                JobOpportunity.first_seen_at,
                JobOpportunity.closed_at,
                JobExtraction.attributes_json,
            )
            .select_from(JobOpportunity)
            .join(evaluation, evaluation.match_evaluation_id == latest_evaluation)
            .join(JobExtraction, JobExtraction.job_extraction_id == evaluation.job_extraction_id)
            .where(
                evaluation.fit_score >= minimum,
                evaluation.recommendation != Recommendation.NOT_RECOMMENDED.value,
                JobExtraction.attributes_json.is_not(None),
            )
        )
        replacements = await self._replacements()
        result = []
        for first, closed, attributes in rows.all():
            if not attributes or "output" not in attributes:
                continue
            terms = terms_of(attributes)
            for kind, keys in terms.items():
                terms[kind] = {replacements.get((kind, key), key) for key in keys}
            result.append(_Opportunity(first, closed, terms))
        return result

    # --- computing -----------------------------------------------------------------------------

    async def recompute(
        self,
        owner_id: int,
        search_intent_id: int,
        *,
        relevance_min_score: int = DEFAULT_RELEVANCE_MIN_SCORE,
    ) -> int:
        """Compute the weekly aggregates; returns the number of rows written.

        The first run backfills every week since the first opportunity; later runs recompute the
        last two weeks under the intent's current revision.
        """
        intent = await self._intent(owner_id, search_intent_id)
        revision_id = intent.current_intent_revision_id
        if revision_id is None:
            return 0
        now = self._clock()
        opportunities = await self._relevant(search_intent_id, relevance_min_score)
        this_week = week_start(now)
        existing = await self._session.scalar(
            select(func.count())
            .select_from(TrendWeekly)
            .where(TrendWeekly.search_intent_id == search_intent_id)
        )
        if existing:
            first = this_week - timedelta(weeks=RECOMPUTED_WEEKS - 1)
        elif opportunities:
            first = week_start(min(o.first_seen for o in opportunities))
        else:
            return 0
        weeks = week_range(first, this_week)

        sources = (
            await self._session.execute(
                select(
                    SourceConfiguration.source_configuration_id, SourceConfiguration.created_at
                ).where(SourceConfiguration.owner_id == owner_id)
            )
        ).all()
        version_id = int(
            await self._session.scalar(select(func.max(TaxonomyVersion.taxonomy_version_id))) or 1
        )

        await self._session.execute(
            delete(TrendWeekly).where(
                TrendWeekly.search_intent_id == search_intent_id, TrendWeekly.week_start.in_(weeks)
            )
        )
        written = 0
        for start in weeks:
            begin = datetime(start.year, start.month, start.day, tzinfo=UTC)
            following = begin + timedelta(days=7)
            end = min(following, now)
            digest = source_set_hash(i for i, created in sources if created <= end)
            total_open = sum(1 for o in opportunities if is_open_at(o.first_seen, o.closed, end))
            counts: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
            for opportunity in opportunities:
                opened = is_open_at(opportunity.first_seen, opportunity.closed, end)
                new = begin <= opportunity.first_seen < following
                closed = opportunity.closed is not None and begin <= opportunity.closed < following
                if not (opened or new or closed):
                    continue
                for kind, keys in opportunity.terms.items():
                    for key in keys:
                        cell = counts[(kind, key)]
                        cell[0] += opened
                        cell[1] += new
                        cell[2] += closed
            for (kind, key), (open_count, new_count, closed_count) in counts.items():
                self._session.add(
                    TrendWeekly(
                        owner_id=owner_id,
                        search_intent_id=search_intent_id,
                        intent_revision_id=revision_id,
                        taxonomy_version_id=version_id,
                        week_start=start,
                        term_kind=kind,
                        term_key=key,
                        relevance_min_score=relevance_min_score,
                        open_count=open_count,
                        new_count=new_count,
                        closed_count=closed_count,
                        relevant_total_open=total_open,
                        source_set_hash=digest,
                        computed_at=now,
                    )
                )
                written += 1
        await self._session.flush()
        return written

    # --- reporting -----------------------------------------------------------------------------

    async def report(
        self,
        owner_id: int,
        search_intent_id: int,
        *,
        kind: str,
        weeks: int,
        limit: int = 15,
    ) -> TrendReport:
        """Return the ranked terms of ``kind`` with weekly series over the last ``weeks`` weeks."""
        await self._intent(owner_id, search_intent_id)
        this_week = week_start(self._clock())
        stored = (
            (
                await self._session.execute(
                    select(TrendWeekly).where(TrendWeekly.search_intent_id == search_intent_id)
                )
            )
            .scalars()
            .all()
        )
        if not stored:
            return TrendReport(
                kind,
                search_intent_id,
                DEFAULT_RELEVANCE_MIN_SCORE,
                0,
                None,
                period_availability(0),
                [],
                [],
                [],
                [],
            )
        first = min(r.week_start for r in stored)
        available = len(week_range(first, this_week))
        shown = week_range(max(first, this_week - timedelta(weeks=weeks - 1)), this_week)

        meta: dict[date, WeekMeta] = {}
        for row in stored:
            meta.setdefault(
                row.week_start,
                WeekMeta(
                    row.week_start,
                    row.relevant_total_open,
                    row.intent_revision_id,
                    row.source_set_hash,
                ),
            )
        totals = {w: meta[w].relevant_total_open if w in meta else 0 for w in shown}
        by_term: dict[str, dict[date, int]] = defaultdict(dict)
        for row in stored:
            if row.term_kind == kind and row.week_start in totals:
                by_term[row.term_key][row.week_start] = row.open_count

        labels = await self._labels(kind, list(by_term))
        rows = []
        for key, per_week in by_term.items():
            series = [
                SeriesPoint(w, per_week.get(w, 0), share(per_week.get(w, 0), totals[w]))
                for w in shown
            ]
            rows.append(
                TrendRow(
                    term_key=key,
                    label=labels.get(key, key),
                    open_now=series[-1].open_count,
                    share_now=series[-1].share,
                    share_change=change_between([p.share for p in series]),
                    count_change=series[-1].open_count - series[0].open_count,
                    series=series,
                )
            )
        rows.sort(key=lambda r: (-r.open_now, r.label.lower()))
        known = sorted(meta.values(), key=lambda m: m.week_start)
        return TrendReport(
            kind=kind,
            search_intent_id=search_intent_id,
            relevance_min_score=stored[0].relevance_min_score,
            available_weeks=available,
            first_week=first,
            periods=period_availability(available),
            weeks=[meta.get(w, WeekMeta(w, 0, None, None)) for w in shown],
            rows=rows[:limit],
            intent_revision_changes=change_points(
                [(m.week_start, m.intent_revision_id) for m in known]
            ),
            source_set_changes=change_points([(m.week_start, m.source_set_hash) for m in known]),
        )

    async def _labels(self, kind: str, keys: list[str]) -> dict[str, str]:
        if not keys:
            return {}
        if kind == TrendTermKind.SKILL.value:
            ids = [int(k) for k in keys if k.isdigit()]
            rows = await self._session.execute(
                select(Skill.skill_id, Skill.canonical_name).where(Skill.skill_id.in_(ids))
            )
            return {str(i): name for i, name in rows.all()}
        terms = await self._session.execute(
            select(TaxonomyTerm.term_key, TaxonomyTerm.label).where(
                TaxonomyTerm.kind == kind, TaxonomyTerm.term_key.in_(keys)
            )
        )
        return dict(terms.all())


class TrendRunner:
    """Runs the trends job for the owner's enabled intents when it is due (used by the worker)."""

    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        *,
        clock: Clock = _utc_now,
        every: timedelta = timedelta(hours=24),
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._every = every

    async def run_due(self, owner_id: int, *, only_intent: int | None = None) -> int:
        """Recompute each enabled intent whose aggregates are older than ``every``; return rows."""
        now = self._clock()
        written = 0
        async with self._session_factory() as session:
            statement = select(SearchIntent.search_intent_id).where(
                SearchIntent.owner_id == owner_id, SearchIntent.enabled.is_(True)
            )
            if only_intent is not None:
                statement = statement.where(SearchIntent.search_intent_id == only_intent)
            service = TrendService(session, clock=self._clock)
            for intent_id in (await session.execute(statement)).scalars().all():
                newest = await session.scalar(
                    select(func.max(TrendWeekly.computed_at)).where(
                        TrendWeekly.search_intent_id == intent_id
                    )
                )
                if newest is not None and now - newest < self._every:
                    continue
                written += await service.recompute(owner_id, intent_id)
            await session.commit()
        return written
