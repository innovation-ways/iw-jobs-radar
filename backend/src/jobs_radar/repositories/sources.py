"""Data access for configured sources and their status (ADR-012)."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.core.errors import NotFoundError
from jobs_radar.db.models import SourceConfiguration, SourceRunResult
from jobs_radar.domain.enums import SourceType


class SourceRepository:
    """Reads and writes ``source_configuration`` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        owner_id: int,
        company_id: int,
        source_type: SourceType,
        external_identifier: str,
        display_name: str,
        url: str,
        enabled: bool,
        rate_limit_per_minute: int = 6,
    ) -> SourceConfiguration:
        """Create a source; server-generated columns are loaded before returning."""
        source = SourceConfiguration(
            owner_id=owner_id,
            company_id=company_id,
            source_type=source_type.value,
            external_identifier=external_identifier,
            display_name=display_name,
            url=url,
            enabled=enabled,
            rate_limit_per_minute=rate_limit_per_minute,
            config_json={},
        )
        self._session.add(source)
        await self._session.flush()
        await self._session.refresh(source)
        return source

    async def get(
        self, owner_id: int, source_configuration_id: int, *, for_update: bool = False
    ) -> SourceConfiguration:
        """Return the owner's source; raises ``NotFoundError`` for unknown or foreign ids."""
        statement = select(SourceConfiguration).where(
            SourceConfiguration.source_configuration_id == source_configuration_id,
            SourceConfiguration.owner_id == owner_id,
        )
        if for_update:
            statement = statement.with_for_update()
        source = (await self._session.execute(statement)).scalar_one_or_none()
        if source is None:
            msg = "Source not found."
            raise NotFoundError(msg)
        return source

    async def find(
        self, owner_id: int, source_type: SourceType, external_identifier: str
    ) -> SourceConfiguration | None:
        """Return the source for this board, if it is already configured."""
        return (
            await self._session.execute(
                select(SourceConfiguration).where(
                    SourceConfiguration.owner_id == owner_id,
                    SourceConfiguration.source_type == source_type.value,
                    SourceConfiguration.external_identifier == external_identifier,
                )
            )
        ).scalar_one_or_none()

    async def list_for_owner(
        self, owner_id: int, *, only_enabled: bool = False
    ) -> list[SourceConfiguration]:
        """Return the owner's sources ordered by name."""
        statement = select(SourceConfiguration).where(SourceConfiguration.owner_id == owner_id)
        if only_enabled:
            statement = statement.where(SourceConfiguration.enabled.is_(True))
        statement = statement.order_by(
            SourceConfiguration.display_name, SourceConfiguration.source_configuration_id
        )
        return list((await self._session.execute(statement)).scalars())

    async def latest_results(self, source_ids: Sequence[int]) -> dict[int, SourceRunResult]:
        """Return the most recent run result of each source (sources that never ran are absent)."""
        if not source_ids:
            return {}
        latest = (
            select(func.max(SourceRunResult.source_run_result_id))
            .where(SourceRunResult.source_configuration_id.in_(source_ids))
            .group_by(SourceRunResult.source_configuration_id)
        )
        rows = await self._session.execute(
            select(SourceRunResult).where(SourceRunResult.source_run_result_id.in_(latest))
        )
        return {row.source_configuration_id: row for row in rows.scalars()}
