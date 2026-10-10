"""The test sample of ADR-057: judge chosen jobs and show what a weight would do.

Run before the weight of the career-direction dimension is raised. For each chosen posting it
judges the enabled directions (stored like any judgement, with new evaluations appended), then
reports the score before, the score now and the score the owner would get with other weights (a
what-if that is never stored), plus the winning direction and the quote behind it.
"""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.providers.base import ExtractionProvider
from jobs_radar.db.models import Company, JobPosting, JobSnapshot
from jobs_radar.domain.enums import DIRECTION_PROMPT_VERSION
from jobs_radar.repositories.directions import DirectionRepository
from jobs_radar.repositories.evaluations import EvaluationRepository
from jobs_radar.services.direction_service import DirectionService
from jobs_radar.services.evaluation import EvaluationService

_ORDER = {"strong": 4, "partial": 3, "weak": 2, "none": 1, "unknown": 0}


@dataclass(frozen=True)
class SampleRow:
    """One job of the sample."""

    job_posting_id: int
    company: str
    title: str
    before_fit: int | None
    after_fit: int | None
    what_if_fit: int | None
    winner: str | None
    levels: dict[str, str] = field(default_factory=dict)
    job_quote: str | None = None
    skipped: str | None = None


@dataclass(frozen=True)
class _Scoring:
    """What is needed to score one snapshot without storing it."""

    evaluator: EvaluationService
    owner_id: int
    job_snapshot_id: int
    job_extraction_id: int
    profile_revision_id: int
    intent_revision_id: int

    async def fit(self, weights: dict[str, int] | None = None) -> int:
        """Return the fit score, with other weights if given (nothing is stored)."""
        result = await self.evaluator.preview(
            self.owner_id,
            job_snapshot_id=self.job_snapshot_id,
            job_extraction_id=self.job_extraction_id,
            profile_revision_id=self.profile_revision_id,
            intent_revision_id=self.intent_revision_id,
            weights=weights,
        )
        return result.fit_score


def _skipped(posting_id: int, company: str, title: str, why: str) -> SampleRow:
    return SampleRow(posting_id, company, title, None, None, None, None, skipped=why)


async def run_sample(
    session: AsyncSession,
    provider: ExtractionProvider,
    owner_id: int,
    posting_ids: list[int],
    *,
    max_chars: int,
    what_if: dict[str, int],
    rejudge: bool = False,
) -> list[SampleRow]:
    """Judge the postings and report them. The caller owns the transaction.

    Raises:
        DirectionUnavailable: the model could not be reached.
    """
    service = DirectionService(session, provider, max_chars=max_chars)
    evaluator = EvaluationService(session, provider=None)
    evaluations = EvaluationRepository(session)
    directions = DirectionRepository(session)
    contexts = await service.contexts(owner_id)
    rows: list[SampleRow] = []
    for posting_id in posting_ids:
        posting = await session.get(JobPosting, posting_id)
        if posting is None:
            continue
        company = await session.get(Company, posting.company_id)
        name = company.canonical_name if company else ""
        if not contexts:
            rows.append(_skipped(posting_id, name, posting.title, "no enabled career direction"))
            continue
        found = await evaluations.latest_extraction(posting_id)
        if found is None:
            rows.append(_skipped(posting_id, name, posting.title, "the job has not been extracted"))
            continue
        snapshot_id, extraction_id = found
        context = contexts[0]
        profile_revision_id = context.profile_revision.profile_revision_id
        intent_revision_id = context.intent.current_intent_revision_id or 0

        scoring = _Scoring(
            evaluator,
            owner_id,
            snapshot_id,
            extraction_id,
            profile_revision_id,
            intent_revision_id,
        )
        before = await scoring.fit()
        await service.assess(owner_id, posting_id, rejudge=rejudge)
        after = await scoring.fit()
        projected = await scoring.fit(what_if)
        judged = await directions.latest(
            snapshot_id, context.targets.keys(), DIRECTION_PROMPT_VERSION
        )
        levels = {context.targets[h].label: row.level for h, row in judged.items()}
        best = max(judged, key=lambda h: _ORDER[judged[h].level], default=None)
        snapshot = await session.get(JobSnapshot, snapshot_id)
        rows.append(
            SampleRow(
                job_posting_id=posting_id,
                company=name,
                title=snapshot.normalised_json["title"] if snapshot else posting.title,
                before_fit=before,
                after_fit=after,
                what_if_fit=projected,
                winner=context.targets[best].label if best else None,
                levels=levels,
                job_quote=judged[best].job_quote if best else None,
            )
        )
    return rows


def render_report(rows: list[SampleRow], what_if: dict[str, int]) -> str:
    """Return the sample as a Markdown table the owner can read and judge."""
    weights = ", ".join(f"{key}={value}" for key, value in what_if.items())
    lines = [
        f"What-if weights: {weights}",
        "",
        "| Company | Job | Before | Now | What-if | Best direction | Levels | Quote |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        if row.skipped:
            lines.append(
                f"| {row.company} | {row.title} | - | - | - | skipped: {row.skipped} | | |"
            )
            continue
        levels = ", ".join(f"{label}: {level}" for label, level in row.levels.items())
        quote = (row.job_quote or "").replace("|", "/")
        lines.append(
            f"| {row.company} | {row.title} | {row.before_fit} | {row.after_fit} | "
            f"{row.what_if_fit} | {row.winner or '-'} | {levels} | {quote} |"
        )
    return "\n".join(lines) + "\n"
