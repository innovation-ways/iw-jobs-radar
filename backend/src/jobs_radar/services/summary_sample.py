"""The test sample of ADR-059: summarise the best-ranked open jobs and show what came out.

The worker only summarises jobs first seen after the feature was released. To check the feature
on jobs the owner really reads, the sample takes the unread, not set-aside jobs with the highest
fit for the first enabled intent, writes their summaries with the chosen local model (stored like
any other) and reports them for the owner to judge.
"""

import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.providers.base import ExtractionProvider
from jobs_radar.db.models import Company, JobPosting
from jobs_radar.services.inbox import InboxFilters, InboxService
from jobs_radar.services.job_summary import SummaryService, SummaryUnavailable


@dataclass(frozen=True)
class SampleRow:
    """One job of the sample."""

    job_posting_id: int
    company: str
    title: str
    fit: int | None
    status: str
    summary: str | None
    seconds: float


async def top_postings(
    session: AsyncSession, owner_id: int, limit: int, *, company: str | None = None
) -> list[tuple[int, int | None]]:
    """Return ``(posting id, fit)`` of the ``limit`` best-ranked jobs still to review."""
    page = await InboxService(session).list_items(
        owner_id,
        InboxFilters(
            state="unread", sort="fit_desc", evaluated=True, set_aside=False, company=company
        ),
        limit=limit,
    )
    return [
        (row.job_posting_id, row.evaluation.fit_score if row.evaluation else None)
        for row in page.rows
    ]


async def run_sample(
    session: AsyncSession,
    provider: ExtractionProvider,
    postings: list[tuple[int, int | None]],
    *,
    max_chars: int,
) -> list[SampleRow]:
    """Write the summaries and report them. The caller owns the transaction.

    A job whose answer stays unusable is reported as ``failed`` and the sample goes on.

    Raises:
        SummaryUnavailable: the model could not be reached.
    """
    service = SummaryService(session, provider, max_chars=max_chars)
    rows: list[SampleRow] = []
    for posting_id, fit in postings:
        posting = await session.get(JobPosting, posting_id)
        if posting is None:
            continue
        company = await session.get(Company, posting.company_id)
        started = time.monotonic()
        result = await service.summarise(posting_id)
        seconds = time.monotonic() - started
        status = (
            "failed" if result.text is None else "written" if result.created else "already there"
        )
        rows.append(
            SampleRow(
                job_posting_id=posting_id,
                company=company.canonical_name if company else "",
                title=posting.title,
                fit=fit,
                status=status,
                summary=result.text,
                seconds=seconds,
            )
        )
    return rows


def render_report(rows: list[SampleRow]) -> str:
    """Return the sample as Markdown the owner can read and judge."""
    lines = [f"{len(rows)} jobs", ""]
    for row in rows:
        fit = "-" if row.fit is None else str(row.fit)
        lines += [
            f"## {row.company} - {row.title}",
            f"posting {row.job_posting_id} | fit {fit} | {row.status} | {row.seconds:.1f}s",
            "",
            row.summary or "(no summary)",
            "",
        ]
    return "\n".join(lines)


__all__ = ["SampleRow", "SummaryUnavailable", "render_report", "run_sample", "top_postings"]
