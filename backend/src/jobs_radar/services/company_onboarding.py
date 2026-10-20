"""Follow a company from its website and careers addresses (ADR-070).

``detect`` normalises the addresses, asks the detector what the careers page can be collected from
and reports it; it writes nothing. ``confirm`` creates everything in the caller's transaction: the
company (matched by normalised name, so an employer already known from a job board is reused), its
website and careers address, the chosen source through the ordinary :class:`SourceService` path
(same validation, defaults and rate limits), the opt-in filters of ADR-051, and the follow state.
The caller commits and then queues the first run.
"""

from dataclasses import dataclass
from typing import Protocol

from jobs_radar.adapters.sources.detector import Candidate, Detection, DetectionOutcome
from jobs_radar.core.errors import InputValidationError
from jobs_radar.db.models import Company, SourceConfiguration
from jobs_radar.domain.careers_markers import normalise_https_address
from jobs_radar.domain.domains import is_job_board_host
from jobs_radar.domain.enums import SourceCategory, SourceType
from jobs_radar.domain.sources import source_category
from jobs_radar.repositories.companies import CompanyRepository
from jobs_radar.repositories.sources import SourceRepository
from jobs_radar.schemas.page_reader import PageReaderConfig
from jobs_radar.schemas.source_filters import JobBoardFilters
from jobs_radar.services.companies import CompanyService
from jobs_radar.services.sources import SourceService


class Detector(Protocol):
    """Finds the collectable boards behind a careers address."""

    async def detect(self, careers_url: str, *, website_url: str | None = None) -> Detection:
        """Return what the careers address leads to."""
        ...


@dataclass(frozen=True)
class OnboardingDetection:
    """A detection with the addresses as they would be saved and the company it matches."""

    outcome: str
    website_url: str
    careers_url: str
    candidates: tuple[Candidate, ...]
    reason: str | None
    existing_company_id: int | None


@dataclass(frozen=True)
class OnboardingResult:
    """The company, its followed state, and the source that was added (if any)."""

    company: Company
    source: SourceConfiguration | None


def _field_error(field: str, message: str) -> InputValidationError:
    return InputValidationError(message, details={"field": field})


class CompanyOnboardingService:
    """Use cases of the "Follow a company" form. The caller owns the transaction."""

    def __init__(
        self,
        companies: CompanyService,
        sources: SourceService,
        company_repository: CompanyRepository,
        source_repository: SourceRepository,
        detector: Detector,
    ) -> None:
        self._companies = companies
        self._sources = sources
        self._company_repository = company_repository
        self._source_repository = source_repository
        self._detector = detector

    @staticmethod
    def addresses(website_url: str, careers_url: str) -> tuple[str, str]:
        """Return the normalised website and careers addresses.

        Raises:
            InputValidationError: ``details["field"]`` names the address that is not acceptable.
        """
        website = normalise_https_address(website_url)
        if website is None:
            msg = "Enter the company's own website address, for example https://example.com."
            raise _field_error("website_url", msg)
        if is_job_board_host(website):
            raise _field_error("website_url", "That is a job board, not the company's own website.")
        careers = normalise_https_address(careers_url)
        if careers is None:
            msg = "Enter the address of the company's careers page, for example https://example.com/careers."
            raise _field_error("careers_url", msg)
        return website, careers

    @staticmethod
    def _name(name: str) -> str:
        cleaned = " ".join(name.split())
        if not cleaned:
            raise _field_error("name", "Enter the company name.")
        return cleaned

    async def detect(
        self, owner_id: int, *, name: str, website_url: str, careers_url: str
    ) -> OnboardingDetection:
        """Report what the careers page can be collected from; nothing is saved."""
        cleaned = self._name(name)
        website, careers = self.addresses(website_url, careers_url)
        detection = await self._detector.detect(careers, website_url=website)
        company = await self._company_repository.find_by_name(cleaned)
        existing_id = company.company_id if company else None

        configured: list[SourceConfiguration] = []
        for candidate in detection.candidates:
            found = await self._source_repository.find(
                owner_id, candidate.source_type, candidate.identifier
            )
            if found is not None:
                configured.append(found)
        if detection.candidates and len(configured) == len(detection.candidates):
            return OnboardingDetection(
                "already_followed",
                website,
                careers,
                detection.candidates,
                "This board is already configured.",
                configured[0].company_id,
            )
        if (
            company is not None
            and not detection.candidates
            and company.careers_url == careers
            and await self._companies.is_followed(owner_id, company.company_id)
        ):
            return OnboardingDetection(
                "already_followed", website, careers, (), detection.reason, existing_id
            )
        return OnboardingDetection(
            detection.outcome.value,
            website,
            careers,
            detection.candidates,
            detection.reason,
            existing_id,
        )

    async def confirm(
        self,
        owner_id: int,
        *,
        name: str,
        website_url: str,
        careers_url: str,
        source_type: SourceType | None,
        identifier: str | None,
        filters_enabled: bool,
        reader: PageReaderConfig | None = None,
        reader_proposed_by: str | None = None,
    ) -> OnboardingResult:
        """Create the company, follow it and add the chosen board.

        Raises:
            InputValidationError: an address is not acceptable, or the board does not exist.
            ConflictError: the board is already configured.
            DependencyUnavailableError: the board cannot be reached right now.
        """
        cleaned = self._name(name)
        website, careers = self.addresses(website_url, careers_url)
        source: SourceConfiguration | None = None
        if reader is not None and source_type is not None:
            raise InputValidationError(
                "Choose either a detected board or a reader, not both.",
                details={"field": "reader"},
            )
        if reader is not None:
            source = await self._sources.add_page_reader(
                owner_id=owner_id,
                careers_url=careers,
                display_name=cleaned,
                config=reader,
                proposed_by=reader_proposed_by or "owner",
            )
        elif source_type is not None and identifier is not None:
            if source_category(source_type) is not SourceCategory.COMPANY_BOARD:
                raise InputValidationError(
                    "Only a company's own board can be followed here.",
                    details={"field": "source"},
                )
            # The board is checked again against the real source: the form's answer is not trusted.
            source = await self._sources.add(
                owner_id=owner_id,
                source_type=source_type,
                identifier=identifier,
                display_name=cleaned,
            )
        if source is not None:
            if filters_enabled:
                source = await self._sources.update(
                    owner_id,
                    source.source_configuration_id,
                    expected_version=source.version,
                    filters=JobBoardFilters(categories=await self._sources.area_keys(owner_id)),
                )
            company_id = source.company_id
            assert company_id is not None  # noqa: S101  # a company board always has its company
            company = await self._company_repository.get(company_id)
        else:
            company = await self._company_repository.get_or_create(cleaned)
        await self._companies.set_website(company.company_id, website)
        company.careers_url = careers
        await self._companies.set_followed(owner_id, company.company_id, followed=True)
        return OnboardingResult(company, source)


__all__ = [
    "CompanyOnboardingService",
    "DetectionOutcome",
    "OnboardingDetection",
    "OnboardingResult",
]
