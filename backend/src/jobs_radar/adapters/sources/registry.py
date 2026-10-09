"""The job source adapters available in this build, keyed by source type."""

from jobs_radar.adapters.sources.arbeitnow import ArbeitnowAdapter
from jobs_radar.adapters.sources.ashby import AshbyAdapter
from jobs_radar.adapters.sources.base import JobSourceAdapter
from jobs_radar.adapters.sources.greenhouse import GreenhouseAdapter
from jobs_radar.adapters.sources.himalayas import HimalayasAdapter
from jobs_radar.adapters.sources.jobicy import JobicyAdapter
from jobs_radar.adapters.sources.lever import LeverAdapter
from jobs_radar.adapters.sources.smartrecruiters import SmartRecruitersAdapter
from jobs_radar.core.http import build_http_client
from jobs_radar.domain.enums import SourceType


def build_source_adapters() -> dict[SourceType, JobSourceAdapter]:
    """Create the adapters: four company-board ATS and the job boards (ADR-049, ADR-050).

    ITJobs.pt waits for its key (T9.6).
    """
    client = build_http_client()
    return {
        SourceType.GREENHOUSE: GreenhouseAdapter(client),
        SourceType.LEVER: LeverAdapter(client),
        SourceType.ASHBY: AshbyAdapter(client),
        SourceType.SMARTRECRUITERS: SmartRecruitersAdapter(client),
        SourceType.ARBEITNOW: ArbeitnowAdapter(client),
        SourceType.JOBICY: JobicyAdapter(client),
        SourceType.HIMALAYAS: HimalayasAdapter(client),
    }
