"""The Remotive adapter against a recorded synthetic payload (ADR-076)."""

import httpx
import pytest
import respx
from tests.job_board_support import PORTUGAL, build, checkpoint, payload

from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.adapters.sources.remotive import RemotiveAdapter
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters

URL = "https://remotive.com/api/remote-jobs"


def board() -> respx.Route:
    return respx.get(URL).mock(
        return_value=httpx.Response(200, content=payload("remotive", "api.json"))
    )


def test_the_adapter_is_a_catalogue_job_board() -> None:
    assert RemotiveAdapter.source_type is SourceType.REMOTIVE
    assert RemotiveAdapter.entry.catalogue_key == "remotive"


@respx.mock
async def test_collect_makes_one_request_and_filters() -> None:
    route = board()
    result = await build(RemotiveAdapter).collect(checkpoint("remotive"))
    assert route.call_count == 1
    assert [p.external_job_id for p in result.postings] == ["2001", "2002"]
    # A US-only role, a marketing role and an old role.
    assert result.dropped_count == 3
    assert result.truncated is False


@respx.mock
async def test_a_posting_is_mapped_with_company_kind_and_stated_salary() -> None:
    board()
    result = await build(RemotiveAdapter).collect(checkpoint("remotive"))
    posting = result.postings[0]
    assert posting.company_name == "Acme Systems"
    assert posting.title == "Senior Python Engineer"
    assert posting.source_url.endswith("senior-python-engineer-2001")
    assert posting.apply_url == posting.source_url
    assert "Contract role." in posting.description_text
    # The board's own words about contract type and pay are kept for the extraction (ADR-073).
    assert "Job type stated by the board: contract" in posting.description_text
    assert "Salary stated by the board: $60k - $90k" in posting.description_text
    assert posting.locations == ("Worldwide",)
    assert posting.posted_at is not None and posting.posted_at.year == 2026


@respx.mock
async def test_an_empty_salary_is_not_a_stated_salary() -> None:
    board()
    result = await build(RemotiveAdapter).collect(checkpoint("remotive"))
    assert "Salary" not in result.postings[1].description_text
    assert result.postings[1].locations == ("Europe",)


@respx.mock
async def test_without_worldwide_only_postings_naming_the_owner_countries_pass() -> None:
    board()
    scope = LocationScope(frozenset({"PT"}), include_worldwide=False)
    result = await build(RemotiveAdapter).collect(checkpoint("remotive", scope=scope))
    assert [p.external_job_id for p in result.postings] == ["2002"]


@respx.mock
async def test_the_per_run_limit_truncates_the_run() -> None:
    board()
    filters = JobBoardFilters(max_age_days=30, max_postings_per_run=1)
    result = await build(RemotiveAdapter).collect(checkpoint("remotive", filters))
    assert len(result.postings) == 1
    assert result.truncated is True


@respx.mock
async def test_an_answer_without_a_job_list_is_an_invalid_payload() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=b'{"error": "blocked"}'))
    with pytest.raises(SourceError) as error:
        await build(RemotiveAdapter).collect(checkpoint("remotive"))
    assert error.value.error_class is SourceErrorClass.INVALID_PAYLOAD


@respx.mock
async def test_validate_reports_the_matching_count() -> None:
    board()
    info = await build(RemotiveAdapter).validate("remotive", scope=PORTUGAL)
    assert info.name == "Remotive"
    assert info.matching_count == 2


async def test_another_identifier_is_refused() -> None:
    with pytest.raises(SourceError):
        await build(RemotiveAdapter).collect(checkpoint("jobicy"))
