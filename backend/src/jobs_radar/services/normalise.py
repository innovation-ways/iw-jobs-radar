"""Build the normalised job stored with each snapshot (document 13, section 5).

At collection time only what the source states is filled in: title, description text, locations,
dates and provenance. Everything an AI extraction will later supply (work mode, seniority, skills,
pay, sector...) is explicitly ``unknown`` and never guessed (ADR-005).
"""

from typing import Any

from jobs_radar.adapters.sources.base import SourcePosting
from jobs_radar.domain.enums import SourceType
from jobs_radar.domain.job_content import material_fields
from jobs_radar.schemas.job import (
    EducationRequired,
    Employer,
    Employment,
    Location,
    NormalisedJob,
    RemoteEligibility,
    Sectors,
    Seniority,
    SourceInfo,
    UnknownCompensation,
    ValueFact,
    VisaSponsorship,
    WorkArrangement,
)

_UNKNOWN = ValueFact(value=None, status="unknown")


def build_normalised_job(
    posting: SourcePosting, *, company_id: int, source_type: SourceType
) -> NormalisedJob:
    """Normalise a source posting, leaving every unstated attribute unknown."""
    return NormalisedJob(
        title=posting.title,
        description_text=posting.description_text,
        employment=Employment(types=[], hours=_UNKNOWN),
        work_arrangement=WorkArrangement(
            mode=_UNKNOWN,
            remote_eligibility=RemoteEligibility(status="unknown"),
            locations=[Location(raw=location) for location in posting.locations],
        ),
        compensation=UnknownCompensation(status="unknown"),
        seniority=Seniority(status="unknown"),
        sectors=Sectors(status="unknown"),
        employer=Employer(company_id=company_id, type=_UNKNOWN),
        education_required=EducationRequired(status="unknown"),
        visa_sponsorship=VisaSponsorship(status="unknown"),
        posted_at=posting.posted_at,
        source=SourceInfo(
            source_type=source_type,
            external_job_id=posting.external_job_id,
            url=posting.source_url,
            apply_url=posting.apply_url,
            language=posting.language,
        ),
    )


def material_of_job(job: NormalisedJob) -> dict[str, Any]:
    """Return the material fields (for hashing and comparison) of a normalised job."""
    return material_fields(
        title=job.title,
        description_text=job.description_text,
        locations=[location.raw for location in job.work_arrangement.locations],
        apply_url=job.source.apply_url or job.source.url,
    )
