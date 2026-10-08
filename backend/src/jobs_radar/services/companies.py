"""Company list and dossiers (T7). The caller owns the transaction."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.repositories.company_list import CompanyListQueries, CompanyPage, Sort

Clock = Callable[[], datetime]
# Default minimum fit for an offer to count as relevant (document 13, section 11.2).
DEFAULT_RELEVANCE_MIN_SCORE = 45


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CompanyService:
    """Use cases around companies."""

    def __init__(self, session: AsyncSession, *, clock: Clock = _utc_now) -> None:
        self._queries = CompanyListQueries(session)
        self._clock = clock

    async def list_companies(
        self,
        owner_id: int,
        *,
        q: str | None = None,
        window: int = 15,
        sort: Sort = "new",
        search_intent_id: int | None = None,
        relevance_min_score: int = DEFAULT_RELEVANCE_MIN_SCORE,
        relevant_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> CompanyPage:
        """Return companies with new-offer counts for the window (7, 15 or 30 days)."""
        del owner_id  # companies are shared reference data in V1; kept for the per-owner future
        return await self._queries.page(
            now=self._clock(),
            search=q,
            search_intent_id=search_intent_id,
            relevance_min_score=relevance_min_score,
            window=window,
            sort=sort,
            relevant_only=relevant_only,
            limit=limit,
            offset=offset,
        )
