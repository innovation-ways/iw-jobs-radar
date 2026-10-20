"""Builds the demo world by running the real pipeline against the scripted boards and model.

The seed creates the persona's profile and intent, adds the fictional boards through the production
source service, then replays ``WEEKS`` weeks of collection: two worker iterations a week, each one
a real collection run followed by grouping, extraction, scoring, summaries and trends. Finally the
persona triages a few jobs, so the inbox shows every state. The clock is injected, so the history
ends "now" and the digest has something new for today.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobs_radar.core.errors import ConflictError, InputValidationError
from jobs_radar.core.settings import Settings
from jobs_radar.demo.jobs import COMPANIES, SOURCES, WEEKS
from jobs_radar.demo.persona import DEMO_PROFILE_TITLE, demo_intent, demo_profile
from jobs_radar.demo.scripted import DEMO_MODEL, DemoBoards, DemoModel, Timeline
from jobs_radar.domain.enums import LOCAL_OWNER_ID, InboxAction, SourceType
from jobs_radar.repositories.companies import CompanyRepository
from jobs_radar.repositories.taxonomy import TaxonomyRepository
from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.profile_api import ProfileInput
from jobs_radar.services.ai_settings import AiSettingsService
from jobs_radar.services.collection import CollectionService
from jobs_radar.services.companies import CompanyService
from jobs_radar.services.dedup import DedupRunner
from jobs_radar.services.evaluation import EvaluationRunner
from jobs_radar.services.extraction_queue import ExtractionQueue
from jobs_radar.services.inbox import InboxFilters, InboxRowView, InboxRunner, InboxService
from jobs_radar.services.intents import IntentService
from jobs_radar.services.job_summary import SummaryRunner
from jobs_radar.services.profiles import ProfileService
from jobs_radar.services.schedule import ScheduleService
from jobs_radar.services.sources import SourceService
from jobs_radar.services.trends import TrendRunner
from jobs_radar.worker.main import Worker

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# What the persona does with a few jobs: open them, shortlist them, apply, or ignore them.
_OPENED = ("Senior Data Engineer", "Platform Engineer, Kubernetes", "Machine Learning Engineer")
_SHORTLISTED = ("Senior Backend Engineer, Payments", "Staff Data Platform Engineer")
_APPLIED = ("Senior Site Reliability Engineer",)
_IGNORED = ("Junior Backend Developer", "Developer Advocate")
_FOLLOWED = ("parcelwise", "orbitry", "quillstream", "cobaltridge")


@dataclass(frozen=True)
class SeedReport:
    """What the seed produced, for the command's last line and for tests."""

    sources: int
    postings: int
    inbox_items: int
    evaluated: int


class _Clock:
    """A settable clock: the simulated moment the pipeline sees."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


async def seed_demo(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    now: datetime | None = None,
) -> SeedReport:
    """Fill an empty database with the demo world; the history ends at ``now`` (default: now).

    Raises:
        RuntimeError: the database already holds sources (refusing to mix demo and real data).
    """
    end = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
    timeline = Timeline()
    clock = _Clock(end)
    week_zero = end - timedelta(weeks=WEEKS - 1, days=4)
    boards = {t: DemoBoards(t, timeline, week_zero) for t in {s.source_type for s in SOURCES}}
    model = DemoModel()

    async with session_factory() as session:
        if await _has_sources(session):
            msg = "The database already has sources; the demo seed needs an empty database."
            raise RuntimeError(msg)
        await _persona(session)
        await _sources(session, boards)
        # A local model connection (the demo's "model" is a script, but the screens should show
        # job analysis as set up, like a normal installation).
        await AiSettingsService(
            session,
            settings.model_copy(
                update={"extraction_enabled": True, "extraction_model": DEMO_MODEL}
            ),
            box=None,
        ).get(LOCAL_OWNER_ID)
        await ScheduleService(session).update(
            LOCAL_OWNER_ID,
            run_times_local=[time(7, 30)],
            timezone="Europe/Lisbon",
            enabled=True,
            expected_version=(await ScheduleService(session).get(LOCAL_OWNER_ID)).setting.version,
        )
        await session.commit()

    collection = CollectionService(session_factory, boards, clock=clock)
    worker = Worker(
        settings,
        session_factory,
        extraction=ExtractionQueue(session_factory, model, max_chars=12000, clock=clock),
        evaluation=EvaluationRunner(session_factory, model, clock=clock),
        summaries=SummaryRunner(
            session_factory,
            model,
            max_chars=12000,
            since=datetime(2000, 1, 1, tzinfo=UTC),
            clock=clock,
        ),
        dedup=DedupRunner(session_factory),
        inbox=InboxRunner(session_factory, LOCAL_OWNER_ID),
        collection=collection,
        trends=TrendRunner(session_factory, clock=clock, every=timedelta(0)),
    )
    for week in range(WEEKS):
        for half in (0, 1):
            timeline.week, timeline.half = week, half
            timeline.final = week == WEEKS - 1 and half == 1
            clock.now = end - timedelta(weeks=WEEKS - 1 - week) - timedelta(days=4 * (1 - half))
            if timeline.final:
                # The persona has triaged by now, so the last run's pay change reaches a
                # shortlisted job (the digest and the "updated" state need that order).
                await _triage(session_factory, clock.now)
            await collection.request_run(LOCAL_OWNER_ID)
            while await worker.run_once():  # a backlog means the time budget ended the batch
                pass
    return await _report(session_factory)


async def _has_sources(session: AsyncSession) -> bool:
    """Whether any source already exists."""
    return bool(await SourceService(session, {}).list_with_status(LOCAL_OWNER_ID))


async def _persona(session: AsyncSession) -> None:
    """Create the persona's profile and its enabled intent."""
    profiles = await ProfileService(session).create(LOCAL_OWNER_ID, DEMO_PROFILE_TITLE)
    profile_id = profiles.profile.career_profile_id
    await ProfileService(session).save(
        LOCAL_OWNER_ID,
        profile_id,
        ProfileInput.model_validate(demo_profile()),
        expected_current_revision=None,
        change_summary="Demo profile",
    )
    await IntentService(session).create(
        LOCAL_OWNER_ID,
        profile_id,
        IntentDefinition.model_validate(
            demo_intent(await TaxonomyRepository(session).keys_in_order())
        ),
        enabled=True,
    )


async def _sources(session: AsyncSession, boards: dict[SourceType, DemoBoards]) -> None:
    """Add every demo board through the production source service (so validation runs too)."""
    service = SourceService(session, boards)
    for source in SOURCES:
        await service.add(
            owner_id=LOCAL_OWNER_ID,
            source_type=source.source_type,
            identifier=source.identifier,
            enabled=True,
        )


async def _triage(session_factory: SessionFactory, now: datetime) -> None:
    """Act on a few jobs like the persona would and follow some companies."""
    async with session_factory() as session:
        inbox = InboxService(session)
        page = await inbox.list_items(
            LOCAL_OWNER_ID, InboxFilters(state=None, include_closed=True), limit=500
        )
        by_title = {row.title: row for row in page.rows}
        for title in (*_OPENED, *_SHORTLISTED, *_APPLIED):
            await _act(inbox, by_title, title, InboxAction.OPEN)
        for title in _SHORTLISTED:
            await _act(inbox, by_title, title, InboxAction.SHORTLIST)
        for title in _APPLIED:
            await _act(inbox, by_title, title, InboxAction.RECORD_APPLICATION, applied_at=now)
        for title in _IGNORED:
            await _act(inbox, by_title, title, InboxAction.IGNORE, reason="not_interested")
        companies = CompanyRepository(session)
        for key in _FOLLOWED:
            company = await companies.get_or_create(COMPANIES[key].name)
            await CompanyService(session).set_followed(
                LOCAL_OWNER_ID, company.company_id, followed=True
            )
            await CompanyService(session).set_website(company.company_id, COMPANIES[key].website)
        await session.commit()


async def _report(session_factory: SessionFactory) -> SeedReport:
    """Count what the seed produced."""
    async with session_factory() as session:
        page = await InboxService(session).list_items(
            LOCAL_OWNER_ID, InboxFilters(state=None, include_closed=True), limit=500
        )
        evaluated = sum(1 for row in page.rows if row.evaluation is not None)
        return SeedReport(
            sources=len(SOURCES),
            postings=len({row.job_posting_id for row in page.rows}),
            inbox_items=len(page.rows),
            evaluated=evaluated,
        )


async def _act(
    inbox: InboxService,
    by_title: dict[str, InboxRowView],
    title: str,
    action: InboxAction,
    **kwargs: object,
) -> None:
    """Perform one owner action on the job with ``title`` (a missing job is skipped)."""
    row = by_title.get(title)
    if row is None:
        return
    try:
        # The service loads the same ORM object as ``row.item``, so its version stays current.
        await inbox.act(
            LOCAL_OWNER_ID,
            row.item.job_inbox_item_id,
            action,
            expected_version=row.item.version,
            **kwargs,  # type: ignore[arg-type]
        )
    except (ConflictError, InputValidationError):  # not allowed from the current state: skip
        return
