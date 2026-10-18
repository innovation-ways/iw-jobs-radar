"""The demo postings are consistent: description, extraction and board data agree (demo seed)."""

from collections import Counter

import pytest

from jobs_radar.demo.jobs import COMPANIES, JOBS, SOURCES, WEEKS, DemoJob
from jobs_radar.demo.render import render_description, render_extraction
from jobs_radar.domain.taxonomy_additions import TAXONOMY_V2_ADDITIONS
from jobs_radar.domain.taxonomy_seed import TAXONOMY_SEED_V1
from jobs_radar.domain.taxonomy_v3 import TAXONOMY_V3_ADDITIONS
from jobs_radar.schemas.extraction import ExtractionOutput
from jobs_radar.services.extraction_rules import verify_evidence


def _taxonomy() -> dict[str, set[str]]:
    merged = {kind: set(keys) for kind, keys in TAXONOMY_SEED_V1.items()}
    for extra in (TAXONOMY_V2_ADDITIONS, TAXONOMY_V3_ADDITIONS):
        for kind, keys in extra.items():
            merged[kind] |= set(keys)
    return merged


def test_there_is_enough_variety_for_a_screenshot() -> None:
    assert len(JOBS) >= 30
    assert len({job.title for job in JOBS}) == len(JOBS), "titles identify jobs to the script"
    assert len({job.company for job in JOBS}) >= 8
    assert WEEKS >= 8


def test_every_job_points_at_a_known_company_and_source() -> None:
    sources = {source.key for source in SOURCES}
    for job in JOBS:
        assert job.company in COMPANIES, job.title
        assert job.source in sources, job.title
        assert 0 <= job.first_week < WEEKS, job.title
        assert job.last_week is None or job.first_week <= job.last_week < WEEKS, job.title


@pytest.mark.parametrize("job", JOBS, ids=lambda job: job.title)
def test_extraction_is_valid_and_every_quote_is_in_the_text(job: DemoJob) -> None:
    description = render_description(job)
    output = ExtractionOutput.model_validate(render_extraction(job, description))
    checked = verify_evidence(output, job.title, description)
    assert checked.unverified == [], checked.unverified
    taxonomy = _taxonomy()
    assert {family.key for family in output.role_families} <= taxonomy["role_family"]
    for value, kind in (
        (output.seniority_levels.value, "seniority_level"),
        (output.employment_types.value, "engagement_type"),
        (output.benefits_mentioned.value, "benefit"),
    ):
        assert set(value or []) <= taxonomy[kind], (job.title, kind)


def test_the_mix_covers_good_and_poor_fits_and_duplicates() -> None:
    families = Counter(job.role for job in JOBS)
    assert families["backend_engineering"] >= 5
    assert any(job.role in {"sales_account_management", "finance_accounting"} for job in JOBS)
    pairs = Counter((job.company, job.title) for job in JOBS)
    assert any(count > 1 for count in pairs.values()) is False, "duplicates differ in source"
    listed_twice = Counter(job.twin for job in JOBS if job.twin)
    assert listed_twice, "at least one job is also listed on a second board"
