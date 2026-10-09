"""The fixed catalogue of job boards the owner can add (ADR-049.2).

Every entry is reviewed code: the official endpoint, the board's own politeness limits, the terms it
publishes and the attribution it asks for. The owner picks an entry; no URL is ever typed, so the
catalogue cannot be used to reach an arbitrary address (ADR-035). Boards whose terms forbid storing
postings or that would need HTML scraping are deliberately absent (research R-00173).
"""

from dataclasses import dataclass, field
from datetime import date

from jobs_radar.domain.enums import SourceType
from jobs_radar.schemas.source_filters import JOB_BOARD_CATEGORIES, JobBoardFilters

_TERMS_READ_ON = date(2026, 10, 9)


@dataclass(frozen=True)
class CatalogueEntry:
    """One job board: how to reach it, what it asks for and what the owner is told about it."""

    source_type: SourceType
    display_name: str
    coverage_note: str
    homepage_url: str
    endpoint: str
    terms_url: str
    terms_note: str
    attribution_text: str
    # Minimum minutes between two runs of the board; it also limits "Run now".
    min_interval_minutes: int
    rate_limit_per_minute: int
    requires_credential: bool = False
    credential_label: str | None = None
    delay_note: str | None = None
    available_categories: tuple[str, ...] = JOB_BOARD_CATEGORIES
    default_filters: JobBoardFilters = field(default_factory=JobBoardFilters)
    terms_read_on: date = _TERMS_READ_ON
    # False while the adapter is unfinished; the entry then stays out of the owner's list.
    available: bool = True

    @property
    def catalogue_key(self) -> str:
        """Stable key of the entry; it is also the ``external_identifier`` of the source."""
        return self.source_type.value


CATALOGUE: tuple[CatalogueEntry, ...] = (
    CatalogueEntry(
        source_type=SourceType.ARBEITNOW,
        display_name="Arbeitnow",
        coverage_note="Europe · remote and relocation",
        homepage_url="https://www.arbeitnow.com",
        endpoint="https://www.arbeitnow.com/api/job-board-api",
        terms_url="https://www.arbeitnow.com/blog/job-board-api",
        terms_note="Free public API, no key. Please do not abuse it and link back to Arbeitnow.",
        attribution_text="Jobs from Arbeitnow (arbeitnow.com).",
        min_interval_minutes=60,
        rate_limit_per_minute=6,
    ),
    CatalogueEntry(
        source_type=SourceType.JOBICY,
        display_name="Jobicy",
        coverage_note="Remote · Europe filter",
        homepage_url="https://jobicy.com",
        endpoint="https://jobicy.com/api/v2/remote-jobs",
        terms_url="https://github.com/Jobicy/remote-jobs-api",
        terms_note=(
            "Free, no key. Poll at most once an hour, keep the original job link and do not "
            "present listings as original postings."
        ),
        attribution_text="Jobs from Jobicy (jobicy.com).",
        min_interval_minutes=60,
        rate_limit_per_minute=6,
    ),
    CatalogueEntry(
        source_type=SourceType.HIMALAYAS,
        display_name="Himalayas",
        coverage_note="Remote · eligible countries listed per job",
        homepage_url="https://himalayas.app",
        endpoint="https://himalayas.app/jobs/api",
        terms_url="https://himalayas.app/docs/remote-jobs-api",
        terms_note=(
            "Free, no key. Data is refreshed every 24 hours. Show a link back to Himalayas "
            "where the data is displayed."
        ),
        attribution_text="Jobs from Himalayas (himalayas.app).",
        delay_note="The board refreshes its data every 24 hours.",
        min_interval_minutes=360,
        rate_limit_per_minute=30,
    ),
    CatalogueEntry(
        source_type=SourceType.ITJOBS_PT,
        display_name="ITJobs.pt",
        coverage_note="Portugal · IT",
        homepage_url="https://www.itjobs.pt",
        endpoint="https://api.itjobs.pt/job/list.json",
        terms_url="https://www.itjobs.pt/api",
        terms_note=(
            "Free API key, requested by email. The published pages state no usage terms; "
            "confirm them with the key before relying on this board."
        ),
        attribution_text="Jobs from ITJobs.pt (itjobs.pt).",
        min_interval_minutes=360,
        rate_limit_per_minute=6,
        requires_credential=True,
        credential_label="ITJobs API key",
        # Finished in T9.6, once the owner has a key and confirms the response fields.
        available=False,
    ),
)

_BY_KEY = {entry.catalogue_key: entry for entry in CATALOGUE}


def get_entry(catalogue_key: str) -> CatalogueEntry | None:
    """Return the entry with ``catalogue_key``, or ``None`` for an unknown key."""
    return _BY_KEY.get(catalogue_key)


def available_entries() -> tuple[CatalogueEntry, ...]:
    """Entries the owner may add now (unfinished adapters are left out)."""
    return tuple(entry for entry in CATALOGUE if entry.available)
