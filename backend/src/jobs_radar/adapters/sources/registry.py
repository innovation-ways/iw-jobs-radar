"""The job source adapters available in this build, keyed by source type."""

from jobs_radar.adapters.sources.base import JobSourceAdapter
from jobs_radar.adapters.sources.greenhouse import GreenhouseAdapter
from jobs_radar.core.http import build_http_client
from jobs_radar.domain.enums import SourceType


def build_source_adapters() -> dict[SourceType, JobSourceAdapter]:
    """Create the adapters (Greenhouse first; Lever and Ashby follow through the same interface)."""
    return {SourceType.GREENHOUSE: GreenhouseAdapter(build_http_client())}
