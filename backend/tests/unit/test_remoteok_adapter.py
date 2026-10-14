"""The Remote OK adapter against a recorded synthetic payload (ADR-074, research R-00176)."""

import httpx
import pytest
import respx
from tests.job_board_support import PORTUGAL, build, checkpoint, payload

from jobs_radar.adapters.sources.base import SourceError
from jobs_radar.adapters.sources.remoteok import RemoteOkAdapter
from jobs_radar.domain.enums import SourceErrorClass, SourceType
from jobs_radar.domain.job_board_rules import LocationScope
from jobs_radar.schemas.source_filters import JobBoardFilters

URL = "https://remoteok.com/api"


def board() -> respx.Route:
    return respx.get(URL).mock(
        return_value=httpx.Response(200, content=payload("remoteok", "api.json"))
    )


def test_the_adapter_is_a_catalogue_job_board() -> None:
    assert RemoteOkAdapter.source_type is SourceType.REMOTEOK
    assert RemoteOkAdapter.entry.catalogue_key == "remoteok"


@respx.mock
async def test_collect_skips_the_legal_notice_and_filters() -> None:
    route = board()
    result = await build(RemoteOkAdapter).collect(checkpoint("remoteok"))
    assert route.call_count == 1
    assert [p.external_job_id for p in result.postings] == ["1001", "1002"]
    # A US-only role, a marketing role, an old role and a posting without company.
    assert result.dropped_count == 4
    assert result.truncated is False


@respx.mock
async def test_a_posting_is_mapped_with_company_text_tags_and_stated_salary() -> None:
    board()
    result = await build(RemoteOkAdapter).collect(checkpoint("remoteok"))
    posting = result.postings[0]
    assert posting.company_name == "Acme Systems"
    assert posting.title == "Senior Python Engineer"
    assert posting.source_url.endswith("remote-senior-python-engineer-acme-1001")
    assert posting.apply_url == posting.source_url
    assert "Contract role." in posting.description_text
    assert "60000-90000" in posting.description_text
    assert posting.locations == ("Worldwide",)
    assert posting.posted_at is not None and posting.posted_at.year == 2026


@respx.mock
async def test_a_zero_salary_is_not_a_stated_salary() -> None:
    board()
    result = await build(RemoteOkAdapter).collect(checkpoint("remoteok"))
    assert "Salary" not in result.postings[1].description_text
    assert result.postings[1].locations == ("Europe",)


@respx.mock
async def test_without_worldwide_only_postings_naming_the_owner_countries_pass() -> None:
    board()
    scope = LocationScope(frozenset({"PT"}), include_worldwide=False)
    result = await build(RemoteOkAdapter).collect(checkpoint("remoteok", scope=scope))
    assert [p.external_job_id for p in result.postings] == ["1002"]


@respx.mock
async def test_the_per_run_limit_truncates_the_run() -> None:
    board()
    filters = JobBoardFilters(max_age_days=30, max_postings_per_run=1)
    result = await build(RemoteOkAdapter).collect(checkpoint("remoteok", filters))
    assert len(result.postings) == 1
    assert result.truncated is True


@respx.mock
async def test_an_answer_that_is_not_a_list_is_an_invalid_payload() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=b'{"error": "rate"}'))
    with pytest.raises(SourceError) as error:
        await build(RemoteOkAdapter).collect(checkpoint("remoteok"))
    assert error.value.error_class is SourceErrorClass.INVALID_PAYLOAD


@respx.mock
async def test_validate_reports_the_matching_count() -> None:
    board()
    info = await build(RemoteOkAdapter).validate("remoteok", scope=PORTUGAL)
    assert info.name == "Remote OK"
    assert info.matching_count == 2


async def test_another_identifier_is_refused() -> None:
    with pytest.raises(SourceError):
        await build(RemoteOkAdapter).collect(checkpoint("jobicy"))
