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
# A board is read every day, so postings older than this are duplicates of what is already stored;
# a short window also keeps slow, paged boards fast (ADR-063).
JOB_BOARD_MAX_AGE_DAYS = 4


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
    default_filters: JobBoardFilters = field(
        default_factory=lambda: JobBoardFilters(max_age_days=JOB_BOARD_MAX_AGE_DAYS)
    )
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
        source_type=SourceType.WEWORKREMOTELY,
        display_name="We Work Remotely",
        coverage_note="Remote · all roles · eligible countries listed per job",
        homepage_url="https://weworkremotely.com",
        endpoint="https://weworkremotely.com/remote-jobs.rss",
        terms_url="https://weworkremotely.com/api-terms-and-guidelines",
        terms_note=(
            "Public RSS feeds, no key. The board's API terms are reported to forbid copying and "
            "storing its data and to require applying through its site; the owner accepted this "
            "for personal use only (ADR-072). The terms page blocks automated readers, so it could "
            "not be read from here."
        ),
        attribution_text="Jobs from We Work Remotely (weworkremotely.com).",
        delay_note="The feeds are refreshed about once an hour.",
        min_interval_minutes=60,
        rate_limit_per_minute=10,
        # The feeds hold only open postings and about 330 in all, so the short window of the big
        # boards (ADR-063) would drop most of the technical ones (ADR-072.6).
        default_filters=JobBoardFilters(max_age_days=30),
    ),
    CatalogueEntry(
        source_type=SourceType.WORKINGNOMADS,
        display_name="Working Nomads",
        coverage_note="Remote · many independent-contractor roles · location as text",
        homepage_url="https://www.workingnomads.com",
        endpoint="https://www.workingnomads.com/api/exposed_jobs/",
        terms_url="https://www.workingnomads.com",
        terms_note=(
            "Free public JSON, no key. No usage terms were found; keep the link to the original "
            "posting and do not poll more than once an hour."
        ),
        attribution_text="Jobs from Working Nomads (workingnomads.com).",
        min_interval_minutes=60,
        rate_limit_per_minute=6,
        # One answer holds every open posting (a few dozen), so a month is read (ADR-074.4).
        default_filters=JobBoardFilters(max_age_days=30),
    ),
    CatalogueEntry(
        source_type=SourceType.REMOTEOK,
        display_name="Remote OK",
        coverage_note="Remote · about a hundred newest postings · salary when stated",
        homepage_url="https://remoteok.com",
        endpoint="https://remoteok.com/api",
        terms_url="https://remoteok.com/legal",
        terms_note=(
            "Free public API, no key. Link back to the posting on Remote OK, name it as the "
            "source and do not use its logo."
        ),
        attribution_text="Jobs from Remote OK (remoteok.com).",
        min_interval_minutes=60,
        rate_limit_per_minute=6,
        # The answer holds only the newest postings, so a week is read (ADR-074.4).
        default_filters=JobBoardFilters(max_age_days=7),
    ),
    CatalogueEntry(
        source_type=SourceType.REMOTIVE,
        display_name="Remotive",
        coverage_note="Remote · small curated feed · contract type and location requirement stated",
        homepage_url="https://remotive.com",
        endpoint="https://remotive.com/api/remote-jobs",
        terms_url="https://remotive.com/api-documentation",
        terms_note=(
            "Free public API, no key. Link back to the posting on Remotive and name it as the "
            "source; its data is delayed by 24 hours and it asks for at most four requests a day. "
            "Do not submit its jobs to third-party job sites."
        ),
        attribution_text="Jobs from Remotive (remotive.com).",
        delay_note="The board delays its postings by 24 hours.",
        # At most four requests a day are asked for (ADR-076), so six hours between runs.
        min_interval_minutes=360,
        rate_limit_per_minute=2,
        # The free feed holds only a few open postings, so a month is read (ADR-076).
        default_filters=JobBoardFilters(max_age_days=30),
    ),
    CatalogueEntry(
        source_type=SourceType.FREELANCERMAP,
        display_name="freelancermap",
        coverage_note="Freelance and contract IT projects · DACH, UK, EU · contract type stated",
        homepage_url="https://www.freelancermap.com",
        endpoint="https://www.freelancermap.com/sitemaps/projects.xml",
        terms_url="https://www.freelancermap.com/term-and-conditions.html",
        terms_note=(
            "No API or feed: the project pages named in the site's public sitemap are read "
            "(robots.txt allows it). Its terms do not mention automated access; they ask not to "
            "overload the service and to use its information for one's own purposes, so reading "
            "is slow (15 pages a minute, at most 120 a run) and for personal use only (ADR-075)."
        ),
        attribution_text="Projects from freelancermap (freelancermap.com).",
        min_interval_minutes=360,
        rate_limit_per_minute=15,
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
    ),
)

_BY_KEY = {entry.catalogue_key: entry for entry in CATALOGUE}


def get_entry(catalogue_key: str) -> CatalogueEntry | None:
    """Return the entry with ``catalogue_key``, or ``None`` for an unknown key."""
    return _BY_KEY.get(catalogue_key)


def available_entries() -> tuple[CatalogueEntry, ...]:
    """Entries the owner may add now (unfinished adapters are left out)."""
    return tuple(entry for entry in CATALOGUE if entry.available)


def require_entry(catalogue_key: str) -> CatalogueEntry:
    """Return the entry with ``catalogue_key``; raises ``KeyError`` if the catalogue lacks it."""
    return _BY_KEY[catalogue_key]
