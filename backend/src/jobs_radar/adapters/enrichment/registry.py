"""Builds the public-dataset adapters with the deployment's URL policy (ADR-035)."""

from jobs_radar import __version__
from jobs_radar.adapters.enrichment.base import PublicApi
from jobs_radar.adapters.enrichment.github import GitHubAdapter
from jobs_radar.adapters.enrichment.gleif import GleifAdapter
from jobs_radar.adapters.enrichment.website import MAX_PAGE_BYTES, WebsiteReader
from jobs_radar.adapters.enrichment.wikidata import WikidataAdapter
from jobs_radar.adapters.enrichment.wikipedia import WikipediaAdapter
from jobs_radar.core.http import GuardedHttpClient
from jobs_radar.core.url_guard import UrlGuard


def build_enrichment_adapters(
    github_token: str | None = None,
) -> tuple[WikidataAdapter, WikipediaAdapter, GleifAdapter, GitHubAdapter]:
    """Create the adapters; every request is guarded (HTTPS, public addresses) and spaced out."""
    client = GuardedHttpClient(
        guard=UrlGuard(),
        user_agent=f"JobsRadar/{__version__} (personal job-market radar; local use)",
        total_timeout=20.0,
    )
    return (
        WikidataAdapter(PublicApi(client, min_interval=1.0)),
        WikipediaAdapter(PublicApi(client, min_interval=0.5)),
        GleifAdapter(PublicApi(client, min_interval=1.0)),
        GitHubAdapter(PublicApi(client, min_interval=1.0), token=github_token),
    )


def build_website_reader() -> WebsiteReader:
    """Create the reader of company websites: guarded, spaced out, at most 8 pages (ADR-054)."""
    client = GuardedHttpClient(
        guard=UrlGuard(),
        user_agent=f"JobsRadar/{__version__} (personal job-market radar; local use)",
        total_timeout=20.0,
        max_bytes=MAX_PAGE_BYTES,
    )
    return WebsiteReader(client, max_pages=8, min_interval=1.0)
