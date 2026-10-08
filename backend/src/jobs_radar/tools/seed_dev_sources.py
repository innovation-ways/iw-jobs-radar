"""Seed the development watchlist of Greenhouse boards as disabled sources (make seed-dev-sources).

The 14 boards come from research R-00169 (HTTP 200 on 2026-10-07). They are a convenience for local
development only: every source is created disabled, nothing is collected, and no network request is
made (display names are curated here instead of being fetched). The tests never use this list as
fixtures. The owner's real watchlist is managed in the Sources screen.
"""

import asyncio
import sys

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.sources.base import JobSourceAdapter
from jobs_radar.adapters.sources.greenhouse import GreenhouseAdapter
from jobs_radar.core.http import build_http_client
from jobs_radar.core.settings import Settings, get_settings
from jobs_radar.db.session import build_engine, build_session_factory
from jobs_radar.domain.enums import LOCAL_OWNER_ID, SourceType
from jobs_radar.repositories.companies import CompanyRepository
from jobs_radar.repositories.sources import SourceRepository

# (board token, company name)
DEV_BOARDS: tuple[tuple[str, str], ...] = (
    ("anthropic", "Anthropic"),
    ("databricks", "Databricks"),
    ("scaleai", "Scale AI"),
    ("mongodb", "MongoDB"),
    ("datadog", "Datadog"),
    ("cloudflare", "Cloudflare"),
    ("stripe", "Stripe"),
    ("elastic", "Elastic"),
    ("gitlab", "GitLab"),
    ("figma", "Figma"),
    ("airbnb", "Airbnb"),
    ("twilio", "Twilio"),
    ("duolingo", "Duolingo"),
    ("samsara", "Samsara"),
)


async def seed_dev_sources(session: AsyncSession, adapter: JobSourceAdapter, owner_id: int) -> int:
    """Create the missing watchlist boards as disabled sources; return how many were created.

    Boards that already exist are left untouched (the owner may have enabled or renamed them).
    The caller owns the transaction.
    """
    sources, companies = SourceRepository(session), CompanyRepository(session)
    created = 0
    for token, name in DEV_BOARDS:
        if await sources.find(owner_id, SourceType.GREENHOUSE, token) is not None:
            continue
        company = await companies.get_or_create(name)
        await sources.create(
            owner_id=owner_id,
            company_id=company.company_id,
            source_type=SourceType.GREENHOUSE,
            external_identifier=token,
            display_name=name,
            url=adapter.endpoint(token),
            enabled=False,
        )
        created += 1
    return created


def check_environment(settings: Settings) -> None:
    """Refuse to seed anything but a development database."""
    if settings.env != "dev":
        msg = f"Refusing to seed: JOBS_RADAR_ENV is '{settings.env}', not 'dev'."
        raise SystemExit(msg)


async def _run() -> int:
    settings = get_settings()
    check_environment(settings)
    engine = build_engine(settings)
    try:
        async with build_session_factory(engine)() as session:
            created = await seed_dev_sources(
                session, GreenhouseAdapter(build_http_client()), LOCAL_OWNER_ID
            )
            await session.commit()
    finally:
        await engine.dispose()
    print(  # CLI output
        f"Seeded {created} new disabled source(s); {len(DEV_BOARDS) - created} already existed. "
        "Enable the ones you want in the Sources screen."
    )
    return 0


def main() -> int:
    """Entry point for ``python -m jobs_radar.tools.seed_dev_sources``."""
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
