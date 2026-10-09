"""Configuring job sources: validate a board, create it with its company, update it, show status."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.sources.base import BoardInfo, JobSourceAdapter, SourceError
from jobs_radar.adapters.sources.catalogue import get_entry
from jobs_radar.core.errors import (
    ConflictError,
    DependencyUnavailableError,
    InputValidationError,
)
from jobs_radar.db.models import Company, SourceConfiguration, SourceRunResult
from jobs_radar.domain.enums import SourceCategory, SourceErrorClass, SourceType
from jobs_radar.domain.sources import next_run_allowed_at, source_category
from jobs_radar.repositories.companies import CompanyRepository
from jobs_radar.repositories.jobs import JobRepository
from jobs_radar.repositories.runs import RunRepository
from jobs_radar.repositories.sources import SourceRepository

# Failures caused by what the owner typed; every other class means the source itself is unavailable.
_INPUT_ERRORS = {SourceErrorClass.NOT_FOUND, SourceErrorClass.CONFIGURATION}


@dataclass(frozen=True)
class SourceStatusRow:
    """A source with the data the Sources screen needs."""

    source: SourceConfiguration
    company_name: str | None
    open_postings: int
    last_result: SourceRunResult | None
    next_run_allowed_at: datetime | None = None


def translate_source_error(error: SourceError) -> InputValidationError | DependencyUnavailableError:
    """Turn an adapter failure into the API error the owner should see."""
    details = {"error_class": error.error_class.value}
    if error.http_status is not None:
        details["http_status"] = str(error.http_status)
    if error.error_class in _INPUT_ERRORS:
        return InputValidationError(error.message, details=details)
    return DependencyUnavailableError(error.message, details=details)


class SourceService:
    """Use cases around source configuration. The caller owns the transaction."""

    def __init__(
        self, session: AsyncSession, adapters: Mapping[SourceType, JobSourceAdapter]
    ) -> None:
        self._session = session
        self._adapters = adapters
        self._sources = SourceRepository(session)

    def _adapter(self, source_type: SourceType) -> JobSourceAdapter:
        adapter = self._adapters.get(source_type)
        if adapter is None:
            msg = f"Source type '{source_type.value}' is not supported yet."
            raise InputValidationError(
                msg, details={"error_class": SourceErrorClass.CONFIGURATION.value}
            )
        return adapter

    async def validate(self, source_type: SourceType, identifier: str) -> BoardInfo:
        """Check a board against the real source without saving anything."""
        try:
            return await self._adapter(source_type).validate(identifier.strip())
        except SourceError as error:
            raise translate_source_error(error) from error

    async def add(
        self, *, owner_id: int, source_type: SourceType, identifier: str, enabled: bool = True
    ) -> SourceConfiguration:
        """Validate a board and create its source (and company when new).

        Raises:
            ConflictError: if the board is already configured.
            InputValidationError: if the board does not exist or the token is invalid.
            DependencyUnavailableError: if the source cannot be reached right now.
        """
        identifier = identifier.strip()
        if source_category(source_type) is SourceCategory.JOB_BOARD:
            msg = "Job boards are added from the catalogue, not by identifier."
            raise InputValidationError(
                msg, details={"error_class": SourceErrorClass.CONFIGURATION.value}
            )
        if await self._sources.find(owner_id, source_type, identifier) is not None:
            msg = "This board is already configured."
            raise ConflictError(msg, details={"external_identifier": identifier})
        info = await self.validate(source_type, identifier)
        company = await CompanyRepository(self._session).get_or_create(info.name)
        return await self._sources.create(
            owner_id=owner_id,
            company_id=company.company_id,
            source_type=source_type,
            external_identifier=identifier,
            display_name=info.name,
            url=self._adapter(source_type).endpoint(identifier),
            enabled=enabled,
        )

    async def update(
        self,
        owner_id: int,
        source_configuration_id: int,
        *,
        expected_version: int,
        enabled: bool | None = None,
        rate_limit_per_minute: int | None = None,
        display_name: str | None = None,
    ) -> SourceConfiguration:
        """Change a source's settings, checking the version the caller saw.

        Raises:
            NotFoundError: unknown or foreign source.
            ConflictError: if ``expected_version`` is stale.
        """
        source = await self._sources.get(owner_id, source_configuration_id, for_update=True)
        if source.version != expected_version:
            msg = "The source changed since it was loaded."
            raise ConflictError(
                msg, details={"expected": expected_version, "actual": source.version}
            )
        if enabled is not None:
            source.enabled = enabled
        if rate_limit_per_minute is not None:
            source.rate_limit_per_minute = rate_limit_per_minute
        if display_name is not None:
            source.display_name = display_name
        source.version += 1
        await self._session.flush()
        return source

    async def added_types(self, owner_id: int) -> set[SourceType]:
        """Return the source types the owner has already configured."""
        return {
            SourceType(source.source_type)
            for source in await self._sources.list_for_owner(owner_id)
        }

    async def get(self, owner_id: int, source_configuration_id: int) -> SourceConfiguration:
        """Return one of the owner's sources."""
        return await self._sources.get(owner_id, source_configuration_id)

    async def list_with_status(self, owner_id: int) -> list[SourceStatusRow]:
        """Return every source with its company name, open postings and latest result."""
        sources = await self._sources.list_for_owner(owner_id)
        ids = [source.source_configuration_id for source in sources]
        results = await self._sources.latest_results(ids)
        open_counts = await JobRepository(self._session).open_count(ids) if ids else {}
        companies: dict[int, str] = {}
        for source in sources:
            if source.company_id is not None and source.company_id not in companies:
                company = await self._session.get(Company, source.company_id)
                companies[source.company_id] = (
                    company.canonical_name if company else source.display_name
                )
        runs = RunRepository(self._session)
        allowed: dict[int, datetime | None] = {}
        for source in sources:
            entry = (
                get_entry(source.external_identifier)
                if source_category(SourceType(source.source_type)) is SourceCategory.JOB_BOARD
                else None
            )
            if entry is not None:
                last = await runs.last_attempt_finished_at(source.source_configuration_id)
                allowed[source.source_configuration_id] = next_run_allowed_at(
                    last, entry.min_interval_minutes
                )
        return [
            SourceStatusRow(
                source=source,
                next_run_allowed_at=allowed.get(source.source_configuration_id),
                company_name=companies.get(source.company_id)
                if source.company_id is not None
                else None,
                open_postings=open_counts.get(source.source_configuration_id, 0),
                last_result=results.get(source.source_configuration_id),
            )
            for source in sources
        ]
