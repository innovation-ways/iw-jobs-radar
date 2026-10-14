"""The job source adapters available in this build, keyed by source type."""

from jobs_radar.adapters.sources.arbeitnow import ArbeitnowAdapter
from jobs_radar.adapters.sources.ashby import AshbyAdapter
from jobs_radar.adapters.sources.base import JobSourceAdapter
from jobs_radar.adapters.sources.eightfold import EightfoldAdapter
from jobs_radar.adapters.sources.greenhouse import GreenhouseAdapter
from jobs_radar.adapters.sources.himalayas import HimalayasAdapter
from jobs_radar.adapters.sources.itjobs import ItJobsAdapter
from jobs_radar.adapters.sources.jobicy import JobicyAdapter
from jobs_radar.adapters.sources.lever import LeverAdapter
from jobs_radar.adapters.sources.page_config import PageConfigAdapter
from jobs_radar.adapters.sources.page_jsonld import PageJsonLdAdapter
from jobs_radar.adapters.sources.smartrecruiters import SmartRecruitersAdapter
from jobs_radar.core.http import build_http_client
from jobs_radar.domain.enums import SourceType


def build_source_adapters() -> dict[SourceType, JobSourceAdapter]:
    """Create the adapters: company boards, own careers sites and job boards (ADR-049..055, 070).

    ITJobs.pt needs the owner's key and is unverified against the live service (T9.6).
    """
    client = build_http_client()
    return {
        SourceType.GREENHOUSE: GreenhouseAdapter(client),
        SourceType.LEVER: LeverAdapter(client),
        SourceType.ASHBY: AshbyAdapter(client),
        SourceType.SMARTRECRUITERS: SmartRecruitersAdapter(client),
        SourceType.EIGHTFOLD: EightfoldAdapter(client),
        SourceType.PAGE_JSONLD: PageJsonLdAdapter(client),
        SourceType.PAGE_CONFIG: PageConfigAdapter(client),
        SourceType.ARBEITNOW: ArbeitnowAdapter(client),
        SourceType.JOBICY: JobicyAdapter(client),
        SourceType.HIMALAYAS: HimalayasAdapter(client),
        SourceType.ITJOBS_PT: ItJobsAdapter(client),
    }
