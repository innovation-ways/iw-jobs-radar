"""A scriptable job source adapter for tests: no network, fully deterministic."""

from collections.abc import Callable
from datetime import UTC, datetime

from jobs_radar.adapters.sources.base import (
    BoardInfo,
    CollectionResult,
    SourceCheckpoint,
    SourceError,
    SourcePosting,
)
from jobs_radar.domain.enums import SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters


def make_posting(
    external_id: str = "1001",
    *,
    title: str = "Senior AI Solutions Engineer",
    description: str = "Design and evaluate LLM-powered features.",
    locations: tuple[str, ...] = ("Remote - EU",),
    url: str | None = None,
    company_name: str | None = None,
) -> SourcePosting:
    """A synthetic posting; tweak fields to simulate changes."""
    url = url or f"https://jobs.example.test/{external_id}"
    return SourcePosting(
        external_job_id=external_id,
        title=title,
        source_url=url,
        apply_url=url,
        description_text=description,
        locations=locations,
        posted_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        source_updated_at=datetime(2026, 10, 6, 9, 0, tzinfo=UTC),
        departments=("Engineering",),
        language="en",
        raw_payload={"id": external_id, "title": title},
        company_name=company_name,
    )


class FakeAdapter:
    """Returns scripted results, one per ``collect`` call; an exception in the script is raised."""

    source_type = SourceType.GREENHOUSE

    def __init__(
        self,
        script: list[object] | None = None,
        *,
        board: BoardInfo | SourceError | Exception | None = None,
        provider: Callable[[SourceCheckpoint], object] | None = None,
    ) -> None:
        self.script = list(script or [])
        self.board = board or BoardInfo(name="Synthetic Co", postings_count=1)
        self.provider = provider
        self.checkpoints: list[SourceCheckpoint] = []

    def endpoint(self, identifier: str) -> str:
        return f"https://boards.example.test/v1/boards/{identifier}/jobs"

    async def validate(
        self,
        identifier: str,
        credential: str | None = None,
        filters: JobBoardFilters | None = None,
        scope: LocationScope | None = None,
    ) -> BoardInfo:
        if isinstance(self.board, Exception):
            raise self.board
        return self.board

    async def collect(self, checkpoint: SourceCheckpoint) -> CollectionResult:
        self.checkpoints.append(checkpoint)
        item = self.provider(checkpoint) if self.provider else self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        assert isinstance(item, CollectionResult)
        return item


def listing(
    *postings: SourcePosting,
    etag: str | None = 'W/"v1"',
    dropped: int = 0,
    truncated: bool = False,
) -> CollectionResult:
    """A successful, modified listing (job boards also report what the filters dropped)."""
    return CollectionResult(
        "modified",
        tuple(postings),
        etag,
        200,
        12,
        len(postings),
        dropped_count=dropped,
        truncated=truncated,
    )


def not_modified(etag: str | None = 'W/"v1"') -> CollectionResult:
    """A 304 result."""
    return CollectionResult("not_modified", (), etag, 304, 3, None)
