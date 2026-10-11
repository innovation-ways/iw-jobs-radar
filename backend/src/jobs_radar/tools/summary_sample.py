r"""Write the summaries of the best-ranked open jobs and print them (ADR-059).

Run once after the feature is released, to check it on jobs the owner really reads::

    python -m jobs_radar.tools.summary_sample [--top 30 | --ids 12,40,77] [--model qwen3.6:27b]

It uses the local model chosen for job analysis, in its larger variant when one is set for
directions (or ``--model``, on the same local server) and
stores the summaries like any other. ``--top`` takes the unread, not set-aside jobs with the
highest fit for the first enabled intent. A summary already stored for that model is not written
again. Prints a Markdown report: company, title, fit, time taken and the summary.
"""

import argparse
import asyncio
import sys

from jobs_radar.adapters.providers.factory import ProviderSpec, build_provider
from jobs_radar.core.settings import get_settings
from jobs_radar.db.session import build_engine, build_session_factory
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.services.ai_settings import AiSettingsService, build_credential_box
from jobs_radar.services.job_summary import SummaryUnavailable
from jobs_radar.services.summary_sample import render_report, run_sample, top_postings
from jobs_radar.tools.direction_sample import parse_ids

MAX_TOP = 100


async def _run(top: int, ids: list[int] | None, model: str | None) -> str:
    settings = get_settings()
    engine = build_engine(settings)
    try:
        async with build_session_factory(engine)() as session:
            ai = AiSettingsService(session, settings, box=build_credential_box(settings))
            target = await ai.direction_target(LOCAL_OWNER_ID)
            if target is None:
                msg = "Choose a local model for job analysis in AI & privacy first."
                raise SystemExit(msg)
            connection, provider = target
            if model:  # another model on the same local server, for this run only
                provider = build_provider(
                    ProviderSpec(connection.provider_type, connection.endpoint_url or "", model),
                    settings,
                )
            postings: list[tuple[int, int | None]] = (
                [(posting_id, None) for posting_id in ids]
                if ids
                else await top_postings(session, LOCAL_OWNER_ID, top)
            )
            try:
                rows = await run_sample(
                    session, provider, postings, max_chars=settings.extraction_max_chars
                )
            except SummaryUnavailable as error:
                msg = f"The local model could not be reached: {error}"
                raise SystemExit(msg) from error
            await session.commit()
            return render_report(rows)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    """Entry point: print the sample report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=30, help="best-ranked jobs to review (1-100)")
    parser.add_argument("--ids", default=None, help="job posting ids instead, comma separated")
    parser.add_argument("--model", default=None, help="a local model for this run only")
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.top <= MAX_TOP:
            msg = f"top must be between 1 and {MAX_TOP}"
            raise ValueError(msg)
        ids = parse_ids(args.ids) if args.ids else None
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)  # a command-line tool
        return 2
    print(asyncio.run(_run(args.top, ids, args.model)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
