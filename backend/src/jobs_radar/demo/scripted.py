"""Scripted stand-ins for the outside world: job boards and the language model.

They implement the real adapter and provider contracts, so the production services run unchanged;
only the data comes from :mod:`jobs_radar.demo.jobs` instead of the network or a model. Nothing here
opens a socket.
"""

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from jobs_radar.adapters.providers.base import (
    ExtractionRequest,
    ProviderError,
    ProviderOutput,
)
from jobs_radar.adapters.sources.base import (
    BoardInfo,
    CollectionResult,
    SourceCheckpoint,
    SourceError,
    SourcePosting,
)
from jobs_radar.demo.jobs import COMPANIES, JOBS, SOURCES, WEEKS, DemoJob
from jobs_radar.demo.render import render_description, render_extraction
from jobs_radar.domain.enums import ProviderErrorClass, SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters

DEMO_MODEL = "demo-script"
_SOURCES_BY_KEY = {source.key: source for source in SOURCES}
_JOBS_BY_TITLE = {job.title: job for job in JOBS}
# Skills the demo "model" calls related when it judges how a job's skill relates to the profile's.
_RELATED = (
    {"Django", "FastAPI"},
    {"dbt", "SQL", "PostgreSQL"},
    {"PyTorch", "Python"},
    {"Spark", "Apache Airflow", "Kafka"},
    {"Java", "Spring", "Go"},
    {"TypeScript", "React"},
)


@dataclass
class Timeline:
    """Where the simulated clock is: which week, which of its two runs, and the final run."""

    week: int = 0
    half: int = 0
    final: bool = False

    def current(self, job: DemoJob) -> DemoJob:
        """Return ``job`` as it reads at this run (a pay change appears on the final run)."""
        if self.final and job.pay_update is not None:
            return replace(job, pay=job.pay_update)
        return job

    def is_open(self, job: DemoJob) -> bool:
        """Whether ``job`` is on its board at the current run."""
        if self.week < job.first_week:
            return False
        if self.week == job.first_week and job.late and self.half == 0:
            return False
        return job.last_week is None or self.week <= job.last_week


class DemoBoards:
    """A job source adapter that serves the demo postings of the board it is asked for."""

    def __init__(self, source_type: SourceType, timeline: Timeline, week_start: datetime) -> None:
        self.source_type = source_type
        self._timeline = timeline
        self._week_start = week_start

    def endpoint(self, identifier: str) -> str:
        """Return the stored address of a board (fictional; nothing ever connects to it)."""
        return f"https://{self.source_type.value}.demo.example/boards/{identifier}"

    async def validate(
        self,
        identifier: str,
        credential: str | None = None,
        filters: JobBoardFilters | None = None,
        scope: LocationScope | None = None,
    ) -> BoardInfo:
        """Describe a demo board; unknown identifiers are refused like a real unknown board."""
        source = _SOURCES_BY_KEY.get(identifier)
        if source is None:
            raise SourceError(SourceErrorClass.NOT_FOUND, "Unknown demo board.")
        company = COMPANIES[source.company].name if source.company else identifier.title()
        count = sum(1 for job in JOBS if job.source == identifier)
        return BoardInfo(name=company, postings_count=count, matching_count=count)

    async def collect(self, checkpoint: SourceCheckpoint) -> CollectionResult:
        """Return the board's postings at the current run, or fail like the demo script says."""
        source = _SOURCES_BY_KEY[checkpoint.identifier]
        if source.failing and self._timeline.final:
            raise SourceError(
                SourceErrorClass(source.failing),
                "The board asked us to slow down.",
                http_status=429,
            )
        postings = tuple(
            self._posting(self._timeline.current(job))
            for job in JOBS
            if job.source == source.key and self._timeline.is_open(job)
        )
        return CollectionResult("modified", postings, None, 200, 120, len(postings))

    def _posting(self, job: DemoJob) -> SourcePosting:
        """Map a demo job to the shape an adapter returns."""
        posted = self._week_start + timedelta(weeks=job.first_week, days=1)
        slug = (
            job.title.lower().replace(" ", "-").replace(",", "").replace("(", "").replace(")", "")
        )
        url = f"{COMPANIES[job.company].website}/careers/{slug}"
        job_board = _SOURCES_BY_KEY[job.source].company is None
        return SourcePosting(
            external_job_id=slug,
            title=job.title,
            source_url=url,
            apply_url=f"{url}/apply",
            description_text=render_description(job),
            locations=job.places,
            posted_at=posted,
            source_updated_at=posted,
            departments=("Engineering",),
            language="en",
            raw_payload={"demo": True},
            company_name=COMPANIES[job.company].name if job_board else None,
        )


def _summary(job: DemoJob) -> str:
    """Two short paragraphs about ``job``, in the style the summary prompt asks for."""
    company = COMPANIES[job.company].name
    level = job.seniority[0].replace("_", " ")
    where = "fully remote" if job.mode == "remote" else f"{job.mode} in {job.places[0]}"
    stack = ", ".join(job.must) or "no specific technologies"
    pay = ""
    if job.pay:
        form, low, high = job.pay
        pay = f" The pay is EUR {low:,} to {high:,} {'a day' if form == 'day_rate' else 'a year'}."
    first = (
        f"{company} is hiring a {job.title} at {level} level, working {where}. "
        f"The main technologies are {stack}.{pay}"
    )
    second = f"{job.pitch} The posting asks for professional English."
    return f"{first}\n\n{second}"


class DemoModel:
    """A language model that answers from the demo records (extraction, summaries, skill pairs)."""

    # Reported like a local model server so the pipeline recognises it as the configured model;
    # the model name says plainly that it is a script.
    provider = "ollama"
    model = DEMO_MODEL

    async def extract(self, request: ExtractionRequest) -> ProviderOutput:
        """Answer a request according to what it asks for; unknown requests fail like a model."""
        user = request.user
        if request.system.startswith("You judge how skills relate"):
            return ProviderOutput(self._relations(user), 5)
        if user.startswith("Company: "):
            job = self._job(user.split("Job title: ", 1)[1].split("\n", 1)[0], user)
            return ProviderOutput(json.dumps({"summary": _summary(job)}), 5)
        if user.startswith("Title: "):
            job = self._job(user[len("Title: ") :].split("\n", 1)[0], user)
            return ProviderOutput(json.dumps(render_extraction(job, render_description(job))), 5)
        raise ProviderError(
            ProviderErrorClass.INVALID_RESPONSE, "The demo model cannot answer this."
        )

    @staticmethod
    def _job(title: str, text: str = "") -> DemoJob:
        """Find the demo job by title; the revised version when the text shows its new pay."""
        job = _JOBS_BY_TITLE.get(title.strip())
        if job is None:
            raise ProviderError(ProviderErrorClass.INVALID_RESPONSE, "Unknown demo posting.")
        if job.pay_update is not None and f"{job.pay_update[1]:,}" in text:
            return replace(job, pay=job.pay_update)
        return job

    @staticmethod
    def _relations(user: str) -> str:
        """Judge each candidate against the target skill with the small related-skills table."""
        lines = user.splitlines()
        target = lines[0].removeprefix("Skill: ").strip()
        candidates = [
            line.removeprefix("- ").strip() for line in lines[2:] if line.startswith("- ")
        ]
        related = [
            name for name in candidates if any({target, name} <= group for group in _RELATED)
        ]
        return json.dumps(
            {
                "equivalent": [],
                "related": related,
                "unrelated": [name for name in candidates if name not in related],
            }
        )


__all__ = ["WEEKS", "DemoBoards", "DemoModel", "Timeline"]
