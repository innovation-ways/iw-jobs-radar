r"""Judge a chosen sample of jobs against the owner's career directions (ADR-057).

Run before the weight of the dimension is raised::

    python -m jobs_radar.tools.direction_sample --ids 12,40,77 \\
        --what-if career_direction=15,role_responsibilities=10 [--model qwen3.6:27b]

It uses the local model chosen for job analysis (or ``--model``, on the same local server), stores
the judgements like any other, and prints a Markdown table: the score before, the score now and
the score with the what-if weights (never stored), the best direction and the quote behind it.
"""

import argparse
import asyncio
import sys

from jobs_radar.adapters.providers.factory import ProviderSpec, build_provider
from jobs_radar.core.settings import get_settings
from jobs_radar.db.session import build_engine, build_session_factory
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.domain.matching.types import DIMENSION_KEYS
from jobs_radar.services.ai_settings import AiSettingsService, build_credential_box
from jobs_radar.services.direction_sample import render_report, run_sample

MAX_WEIGHT = 40


def parse_ids(text: str) -> list[int]:
    """Parse ``"4,17,9"`` into posting ids."""
    try:
        ids = [int(part) for part in text.split(",")]
    except ValueError as error:
        msg = "ids must be comma-separated numbers"
        raise ValueError(msg) from error
    if not ids or any(i < 1 for i in ids):
        msg = "ids must be positive numbers"
        raise ValueError(msg)
    return ids


def parse_weights(text: str) -> dict[str, int]:
    """Parse ``"career_direction=15,role_responsibilities=10"`` into weights."""
    weights: dict[str, int] = {}
    for part in text.split(","):
        key, _, value = part.strip().partition("=")
        if key not in DIMENSION_KEYS or not value.isdigit() or int(value) > MAX_WEIGHT:
            msg = f"bad weight '{part.strip()}': use dimension=0..{MAX_WEIGHT}"
            raise ValueError(msg)
        weights[key] = int(value)
    return weights


async def _run(ids: list[int], what_if: dict[str, int], model: str | None, *, rejudge: bool) -> str:
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
            rows = await run_sample(
                session,
                provider,
                LOCAL_OWNER_ID,
                ids,
                max_chars=settings.extraction_max_chars,
                what_if=what_if,
                rejudge=rejudge,
            )
            await session.commit()
            return render_report(rows, what_if)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    """Entry point: print the sample report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", required=True, help="job posting ids, comma separated")
    parser.add_argument(
        "--what-if",
        default="career_direction=15,role_responsibilities=10",
        help="weights to preview, never stored",
    )
    parser.add_argument("--model", default=None, help="a local model for this run only")
    parser.add_argument(
        "--rejudge",
        action="store_true",
        help="judge again even if a direction was judged (adds rows; the newest counts)",
    )
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(
            _run(
                parse_ids(args.ids),
                parse_weights(args.what_if),
                args.model,
                rejudge=args.rejudge,
            )
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)  # a command-line tool
        return 2
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
