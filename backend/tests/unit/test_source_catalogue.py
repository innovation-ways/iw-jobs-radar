"""Job board catalogue, source categories and per-source filters (ADR-049, T9.1)."""

from datetime import date
from urllib.parse import urlparse

import pytest
from pydantic import ValidationError

from jobs_radar.adapters.sources.base import SourcePosting
from jobs_radar.adapters.sources.catalogue import CATALOGUE, available_entries, get_entry
from jobs_radar.domain.enums import SourceCategory, SourceErrorClass, SourceType
from jobs_radar.domain.sources import source_category
from jobs_radar.schemas.source_filters import JobBoardFilters

JOB_BOARDS = {
    SourceType.ARBEITNOW,
    SourceType.JOBICY,
    SourceType.HIMALAYAS,
    SourceType.ITJOBS_PT,
}
COMPANY_BOARDS = {SourceType.GREENHOUSE, SourceType.LEVER, SourceType.ASHBY}


# --- categories ---------------------------------------------------------------------------------


@pytest.mark.parametrize("source_type", sorted(COMPANY_BOARDS))
def test_ats_types_are_company_boards(source_type: SourceType) -> None:
    assert source_category(source_type) is SourceCategory.COMPANY_BOARD


@pytest.mark.parametrize("source_type", sorted(JOB_BOARDS))
def test_board_types_are_job_boards(source_type: SourceType) -> None:
    assert source_category(source_type) is SourceCategory.JOB_BOARD


def test_every_source_type_has_a_category() -> None:
    assert set(SourceType) == COMPANY_BOARDS | JOB_BOARDS


def test_authentication_is_a_source_error_class() -> None:
    assert SourceErrorClass.AUTHENTICATION.value == "authentication"


# --- catalogue ----------------------------------------------------------------------------------


def test_catalogue_covers_the_first_wave_job_boards_only() -> None:
    assert {entry.source_type for entry in CATALOGUE} == JOB_BOARDS


def test_catalogue_keys_equal_source_type_values_and_are_unique() -> None:
    keys = [entry.catalogue_key for entry in CATALOGUE]
    assert len(keys) == len(set(keys))
    assert all(entry.catalogue_key == entry.source_type.value for entry in CATALOGUE)


@pytest.mark.parametrize("entry", CATALOGUE, ids=lambda entry: entry.catalogue_key)
def test_entries_are_complete_and_use_https(entry) -> None:  # type: ignore[no-untyped-def]
    for url in (entry.endpoint, entry.terms_url, entry.homepage_url):
        assert urlparse(url).scheme == "https"
    assert entry.display_name and entry.coverage_note and entry.attribution_text
    assert entry.terms_read_on <= date.today()
    assert entry.min_interval_minutes >= 1
    assert 1 <= entry.rate_limit_per_minute <= 60
    assert entry.default_filters.max_postings_per_run <= 5000
    assert entry.available_categories


def test_the_key_is_asked_for_only_where_the_catalogue_says_so() -> None:
    needs_key = {entry.source_type for entry in CATALOGUE if entry.requires_credential}
    assert needs_key == {SourceType.ITJOBS_PT}
    for entry in CATALOGUE:
        assert bool(entry.credential_label) == entry.requires_credential


def test_itjobs_stays_hidden_until_its_adapter_is_finished() -> None:
    assert {entry.source_type for entry in available_entries()} == JOB_BOARDS - {
        SourceType.ITJOBS_PT
    }


def test_get_entry_finds_by_key_and_rejects_unknown_keys() -> None:
    assert get_entry("himalayas").source_type is SourceType.HIMALAYAS
    assert get_entry("greenhouse") is None
    assert get_entry("nope") is None


def test_boards_with_a_delayed_feed_say_so() -> None:
    # Himalayas refreshes once a day; the interval protects the board from needless calls.
    assert get_entry("himalayas").min_interval_minutes >= 60  # type: ignore[union-attr]


# --- filters ------------------------------------------------------------------------------------


def test_filter_defaults_follow_adr_049() -> None:
    filters = JobBoardFilters()
    assert filters.schema_version == 1
    assert filters.country_codes == ["PT"]
    assert filters.include_worldwide is True
    assert filters.max_age_days == 30
    assert filters.max_postings_per_run == 500
    assert filters.search_terms == []
    assert filters.categories == ["software", "data", "devops", "security"]


def test_filters_round_trip_through_json_for_config_json() -> None:
    filters = JobBoardFilters(country_codes=["PT", "ES"], search_terms=["python"], max_age_days=7)
    restored = JobBoardFilters.model_validate(filters.model_dump(mode="json"))
    assert restored == filters


@pytest.mark.parametrize(
    "bad",
    [
        {"country_codes": ["pt"]},
        {"country_codes": ["PRT"]},
        {"max_age_days": 0},
        {"max_age_days": 366},
        {"max_postings_per_run": 0},
        {"max_postings_per_run": 5001},
        {"search_terms": ["x" * 81]},
        {"categories": ["Bad Category"]},
        {"unknown_field": 1},
    ],
)
def test_invalid_filters_are_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        JobBoardFilters(**bad)  # type: ignore[arg-type]


def test_filters_drop_blank_and_duplicate_entries() -> None:
    filters = JobBoardFilters(search_terms=[" python ", "", "python", "Rust"])
    assert filters.search_terms == ["python", "Rust"]


# --- posting contract ---------------------------------------------------------------------------


def test_a_source_posting_may_carry_the_company_name() -> None:
    posting = SourcePosting(
        external_job_id="1",
        title="Engineer",
        source_url="https://x.example.test/1",
        apply_url="https://x.example.test/1",
        description_text="text",
        locations=(),
        posted_at=None,
        source_updated_at=None,
        departments=(),
        language=None,
        raw_payload={},
    )
    assert posting.company_name is None
    assert SourcePosting.__dataclass_fields__["company_name"].default is None
