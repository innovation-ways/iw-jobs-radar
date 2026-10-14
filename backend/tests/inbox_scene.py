"""A synthetic inbox world for tests: a profile, two intents and entries that can be scored."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.db.models import JobInboxItem, JobOpportunity, JobPosting
from jobs_radar.domain.enums import InboxState, Recommendation, SourceType
from jobs_radar.services.inbox import InboxFilters
from tests.factories import (
    make_company,
    make_evaluation,
    make_extraction,
    make_inbox_item,
    make_intent,
    make_opportunity,
    make_posting,
    make_profile,
    make_source,
    unique,
)

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


@dataclass
class Entry:
    item: JobInboxItem
    opportunity: JobOpportunity
    posting: JobPosting
    company: str


class Scene:
    """A profile, two intents and a helper that adds inbox entries (optionally scored)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tag = unique("scene")

    async def setup(self) -> "Scene":
        profile, self.profile_revision = await make_profile(self.session)
        self.intent, self.intent_revision = await make_intent(self.session, profile)
        self.other_intent, self.other_revision = await make_intent(self.session, profile)
        return self

    async def entry(
        self,
        *,
        fit: int | None = None,
        other_fit: int | None = None,
        days: int = 0,
        state: InboxState = InboxState.UNREAD,
        company: str | None = None,
        title: str | None = None,
        source_type: SourceType = SourceType.GREENHOUSE,
        shortlisted: bool = False,
        recommendation: Recommendation = Recommendation.RECOMMENDED,
        attributes: dict[str, Any] | None = None,
    ) -> Entry:
        name = company or f"{self.tag} Co {secrets_suffix()}"
        source = await make_source(
            self.session, await make_company(self.session, name), source_type=source_type
        )
        posting, snapshot = await make_posting(
            self.session,
            source,
            title=title or f"{self.tag} job",
            first_seen_at=T0 + timedelta(days=days),
        )
        opportunity = await make_opportunity(self.session, posting)
        item = await make_inbox_item(self.session, opportunity)
        item.state = state.value
        item.is_shortlisted = shortlisted
        # A stored extraction wraps the model's answer under ``output`` next to its checks.
        stored = {"output": attributes} if attributes is not None else None
        extraction = await make_extraction(self.session, snapshot, attributes=stored)
        if fit is not None:
            await make_evaluation(
                self.session,
                snapshot,
                extraction,
                self.profile_revision,
                self.intent_revision,
                fit_score=fit,
                recommendation=recommendation,
            )
        if other_fit is not None:
            await make_evaluation(
                self.session,
                snapshot,
                extraction,
                self.profile_revision,
                self.other_revision,
                fit_score=other_fit,
            )
        await self.session.flush()
        return Entry(item, opportunity, posting, name)

    def filters(self, **changes: Any) -> InboxFilters:
        base = {
            "search_intent_id": self.intent.search_intent_id,
            "state": None,
            "company": self.tag,
        }
        return InboxFilters(**{**base, **changes})


def secrets_suffix() -> str:
    return secrets.token_hex(3)


async def scene(session: AsyncSession) -> Scene:
    return await Scene(session).setup()
