"""The job source adapters available in this build, keyed by source type."""

from jobs_radar.adapters.sources.arbeitnow import ArbeitnowAdapter
from jobs_radar.adapters.sources.base import JobSourceAdapter
from jobs_radar.adapters.sources.greenhouse import GreenhouseAdapter
from jobs_radar.adapters.sources.himalayas import HimalayasAdapter
from jobs_radar.adapters.sources.jobicy import JobicyAdapter
from jobs_radar.core.http import build_http_client
from jobs_radar.domain.enums import SourceType


def build_source_adapters() -> dict[SourceType, JobSourceAdapter]:
    """Create the adapters: Greenhouse (company boards) and the first-wave job boards (ADR-049).

    Lever and Ashby follow through the same interface; ITJobs.pt waits for its key (T9.6).
    """
    client = build_http_client()
    return {
        SourceType.GREENHOUSE: GreenhouseAdapter(client),
        SourceType.ARBEITNOW: ArbeitnowAdapter(client),
        SourceType.JOBICY: JobicyAdapter(client),
        SourceType.HIMALAYAS: HimalayasAdapter(client),
    }
