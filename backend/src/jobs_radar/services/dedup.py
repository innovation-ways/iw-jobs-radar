"""Grouping listings into real opportunities with ``dedup-v1`` (T4.7, ADR-023).

Every posting belongs to exactly one opportunity. A listing of the same company on another source
with a compatible place and similar text joins the existing opportunity (``auto`` when very
similar, ``possible`` when the owner should look); otherwise it starts its own. Links are
reversible: the owner can confirm or reject one, and a rejected pair is remembered. Nothing here
needs a model; embeddings only improve the description comparison and fall back to shingles.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.providers.base import EmbeddingProvider, ProviderError
from jobs_radar.core.errors import ConflictError
from jobs_radar.db.models import JobOpportunity, JobOpportunityLink, JobPosting, JobSnapshot
from jobs_radar.domain import dedup
from jobs_radar.repositories.dedup import Candidate, DedupRepository

Clock = Callable[[], datetime]
# How much of a description is sent to the embedding model.
_EMBED_CHARS = 6000
_RANK = {"auto": 2, "possible": 1}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _locations(snapshot: JobSnapshot) -> list[str]:
    normalised: dict[str, Any] = snapshot.normalised_json
    return [
        loc["raw"]
        for loc in normalised.get("work_arrangement", {}).get("locations", [])
        if loc.get("raw")
    ]


def _posted_at(posting: JobPosting, snapshot: JobSnapshot) -> datetime:
    raw = snapshot.normalised_json.get("posted_at")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return posting.first_seen_at


class DedupService:
    """Links postings to opportunities. The caller owns the transaction."""

    def __init__(
        self,
        session: AsyncSession,
        embedder: EmbeddingProvider | None = None,
        *,
        clock: Clock = _utc_now,
    ) -> None:
        self._session = session
        self._repository = DedupRepository(session)
        self._embedder = embedder
        self._clock = clock

    async def link_unlinked(self, limit: int = 500) -> int:
        """Link every open posting that has no opportunity yet; return how many were linked."""
        postings = await self._repository.unlinked_postings(limit)
        for posting in postings:
            await self.link_posting(posting.job_posting_id)
        return len(postings)

    async def link_posting(self, job_posting_id: int) -> JobOpportunityLink:
        """Give the posting an opportunity (an existing one if it matches) and return its link."""
        existing = await self._repository.active_link(job_posting_id)
        if existing is not None:
            return existing
        posting = await self._repository.get_posting(job_posting_id)
        snapshot = await self._repository.latest_snapshot(job_posting_id)
        rejected = await self._repository.rejected_opportunity_ids(job_posting_id)

        best: tuple[int, float, Candidate, dedup.Similarity, dedup.Decision] | None = None
        own_vector = await self._embed(snapshot) if self._embedder else None
        for candidate in await self._repository.candidates(posting):
            if candidate.job_opportunity_id in rejected:
                continue  # the owner already said these do not belong together
            scored = await self._compare(posting, snapshot, own_vector, candidate)
            if scored is None:
                continue
            similarity, decision = scored
            if decision == "distinct":
                continue
            key = (_RANK[decision], similarity.score)
            if best is None or key > (best[0], best[1]):
                best = (_RANK[decision], similarity.score, candidate, similarity, decision)

        if best is None:
            opportunity = await self._repository.create_opportunity(posting)
            link = await self._repository.add_link(
                job_opportunity_id=opportunity.job_opportunity_id,
                job_posting_id=job_posting_id,
                state="auto",
                similarity=1.0,
                features={"reason": "no matching listing"},
                method=dedup.POLICY_VERSION,
            )
            return link
        _rank, _score, candidate, similarity, decision = best
        link = await self._repository.add_link(
            job_opportunity_id=candidate.job_opportunity_id,
            job_posting_id=job_posting_id,
            state=decision,
            similarity=similarity.score,
            features={
                **similarity.features,
                "matched_job_posting_id": candidate.posting.job_posting_id,
            },
            method=dedup.POLICY_VERSION,
        )
        await self.refresh_opportunity(candidate.job_opportunity_id)
        return link

    async def _embed(self, snapshot: JobSnapshot) -> list[float] | None:
        if self._embedder is None:
            return None
        text = snapshot.normalised_json.get("description_text", "")[:_EMBED_CHARS]
        try:
            return (await self._embedder.embed([text]))[0]
        # A failing embedding model only means the cheaper text comparison is used instead.
        except ProviderError:
            return None

    async def _compare(
        self,
        posting: JobPosting,
        snapshot: JobSnapshot,
        own_vector: list[float] | None,
        candidate: Candidate,
    ) -> tuple[dedup.Similarity, dedup.Decision] | None:
        location = dedup.location_relation(_locations(snapshot), _locations(candidate.snapshot))
        if location == "none":
            return None
        title = dedup.title_similarity(
            snapshot.normalised_json["title"], candidate.snapshot.normalised_json["title"]
        )
        description, method = await self._description(snapshot, candidate.snapshot, own_vector)
        dates = dedup.date_proximity(
            _posted_at(posting, snapshot), _posted_at(candidate.posting, candidate.snapshot)
        )
        similarity = dedup.similarity(
            title=title, description=description, dates=dates, location=location
        )
        similarity.features["description_method"] = method
        decision = dedup.decide(similarity.score, location, same_source=False)
        return similarity, decision

    async def _description(
        self, mine: JobSnapshot, other: JobSnapshot, own_vector: list[float] | None
    ) -> tuple[float, str]:
        """Return ``(similarity, method)``: cosine of embeddings if possible, else shingles."""
        if self._embedder is not None and own_vector is not None:
            try:
                other_vector = (
                    await self._embedder.embed(
                        [other.normalised_json.get("description_text", "")[:_EMBED_CHARS]]
                    )
                )[0]
                return dedup.cosine(own_vector, other_vector), "embedding"
            except ProviderError:
                pass
        return (
            dedup.jaccard(
                dedup.shingles(mine.normalised_json.get("description_text", "")),
                dedup.shingles(other.normalised_json.get("description_text", "")),
            ),
            "shingles",
        )

    async def refresh_opportunity(self, job_opportunity_id: int) -> JobOpportunity:
        """Recompute first and last seen, closed and the primary posting from its listings."""
        opportunity = await self._repository.opportunity(job_opportunity_id)
        postings = await self._repository.postings_of(job_opportunity_id)
        if not postings:
            return opportunity
        closed = [p.closed_at for p in postings]
        await self._repository.update_aggregates(
            opportunity,
            primary=dedup.choose_primary(
                [
                    dedup.PrimaryCandidate(p.job_posting_id, p.source_type, p.first_seen_at)
                    for p in postings
                ]
            ),
            first_seen_at=min(p.first_seen_at for p in postings),
            last_seen_at=max(p.last_seen_at for p in postings),
            closed_at=None
            if any(c is None for c in closed)
            else max(c for c in closed if c is not None),
        )
        return opportunity

    async def refresh_stale(self, limit: int = 1000) -> int:
        """Bring opportunities in line with their listings; return how many were changed.

        Collection closes a posting after two runs without it and reopens it when it returns, but
        only here does the opportunity (and so the inbox) learn about it.
        """
        ids = await self._repository.stale_closed(limit)
        for job_opportunity_id in ids:
            await self.refresh_opportunity(job_opportunity_id)
        return len(ids)

    async def confirm(self, job_opportunity_link_id: int) -> JobOpportunityLink:
        """Record that the owner confirmed a link.

        Raises:
            NotFoundError: unknown link.
            ConflictError: the link was already rejected.
        """
        link = await self._repository.get_link(job_opportunity_link_id)
        if link.state == "rejected":
            msg = "This link was already rejected."
            raise ConflictError(msg)
        link.state = "confirmed"
        link.decided_by_user_at = self._clock()
        await self._session.flush()
        return link

    async def reject(self, job_opportunity_link_id: int) -> JobOpportunity:
        """Record that the owner rejected a link; the posting gets an opportunity of its own.

        The rejected link is kept as history so the same pair is not proposed again.

        Raises:
            NotFoundError: unknown link.
            ConflictError: the link was already rejected or is the opportunity's only listing.
        """
        link = await self._repository.get_link(job_opportunity_link_id)
        if link.state == "rejected":
            msg = "This link was already rejected."
            raise ConflictError(msg)
        if await self._repository.count_postings(link.job_opportunity_id) <= 1:
            msg = "There is nothing to separate: this is the only listing of the opportunity."
            raise ConflictError(msg)
        posting = await self._repository.get_posting(link.job_posting_id)
        old_opportunity_id = link.job_opportunity_id
        link.state = "rejected"
        link.decided_by_user_at = self._clock()
        await self._session.flush()
        opportunity = await self._repository.create_opportunity(posting)
        await self._repository.add_link(
            job_opportunity_id=opportunity.job_opportunity_id,
            job_posting_id=posting.job_posting_id,
            state="auto",
            similarity=1.0,
            features={"reason": "separated by the owner"},
            method=dedup.POLICY_VERSION,
        )
        await self.refresh_opportunity(old_opportunity_id)
        return opportunity


class DedupRunner:
    """Groups new postings into opportunities in its own transaction (used by the worker)."""

    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._embedder = embedder

    async def run(self, limit: int = 500) -> int:
        """Link postings that belong to no opportunity yet; return how many were linked."""
        async with self._session_factory() as session:
            service = DedupService(session, self._embedder)
            linked = await service.link_unlinked(limit)
            await service.refresh_stale()
            await session.commit()
            return linked
