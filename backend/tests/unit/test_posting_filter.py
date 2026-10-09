"""The pre-filter of company boards: areas and location before storage (ADR-051)."""

from datetime import UTC, datetime, timedelta

import pytest
from tests.fake_adapter import make_posting

from jobs_radar.adapters.sources.posting_filter import apply_filters, keep_posting
from jobs_radar.domain.job_board_rules import LocationScope, OnsiteArea
from jobs_radar.schemas.source_filters import JobBoardFilters

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
LISBON = OnsiteArea("Lisbon", 38.72, -9.14, 40)
SCOPE = LocationScope(frozenset({"PT"}), include_worldwide=True, onsite_areas=(LISBON,))
FILTERS = JobBoardFilters()


def posting(
    title: str = "Senior Backend Engineer", locations: tuple[str, ...] = ("Remote - EU",), **kw
):
    base = make_posting(
        "1", title=title, locations=locations, description=kw.pop("description", "Build.")
    )
    from dataclasses import replace

    return replace(base, **kw)


def keep(p, filters: JobBoardFilters = FILTERS, scope: LocationScope | None = SCOPE) -> bool:
    return keep_posting(p, filters, scope, NOW)


# --- areas, terms, age -------------------------------------------------------------------------


def test_a_posting_in_a_chosen_area_is_kept_and_others_are_dropped() -> None:
    assert keep(posting("Senior Backend Engineer"))
    assert not keep(posting("Account Executive"))
    assert not keep(posting("Gujarati PDF Annotation Specialist"))


def test_the_departments_count_towards_the_area() -> None:
    assert keep(posting("Specialist", departments=("Data Platform",)))


def test_no_chosen_area_keeps_every_area() -> None:
    assert keep(posting("Account Executive"), JobBoardFilters(categories=[]))


def test_search_terms_must_match() -> None:
    assert keep(posting(description="We use Rust."), JobBoardFilters(search_terms=["rust"]))
    assert not keep(posting(description="We use Java."), JobBoardFilters(search_terms=["rust"]))


def test_old_postings_are_dropped_but_an_unknown_date_is_kept() -> None:
    assert not keep(posting(posted_at=NOW - timedelta(days=60)))
    assert keep(posting(posted_at=NOW - timedelta(days=5)))
    assert keep(posting(posted_at=None))


# --- location ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("locations", "expected"),
    [
        (("Remote - EU",), True),
        (("Remote - Portugal",), True),
        (("Remote, Europe",), True),
        (("Remote - US",), False),
        (("Remote - Germany",), False),
        (("Remote",), True),  # nothing stated: judged later
        (("Anywhere",), True),
        (("Worldwide",), True),
        (("Lisbon, Portugal",), True),
        (("Lisboa",), True),
        (("Setúbal, Portugal",), True),  # inside 40 km
        (("Porto, Portugal",), False),
        (("Berlin, Germany",), False),
        (("San Francisco, CA",), False),
        (("Lisbon", "Berlin"), True),  # any place that works is enough
        (("Berlin", "Remote - EU"), True),
        (("Madrid", "Berlin"), False),
        (("HQ campus",), True),  # a place that cannot be read is judged later
        (("Spain", "United Kingdom"), False),  # a bare country is where the person may live
        (("United States",), False),
        (("Portugal",), True),
        (("Greece", "Portugal"), True),
        (("Hybrid", "Austin, TX, United States"), False),  # "Hybrid" is a marker, not a place
        (("In-Office", "London, United Kingdom"), False),
        (("Hybrid", "Lisboa, Lisboa, Portugal"), True),
        (("Hybrid",), True),
        ((), True),
    ],
)
def test_location_follows_the_scope(locations: tuple[str, ...], expected: bool) -> None:
    assert keep(posting(locations=locations)) is expected


def test_worldwide_postings_need_an_intent_that_accepts_remote_work() -> None:
    scope = LocationScope(frozenset({"PT"}), include_worldwide=False, onsite_areas=(LISBON,))
    assert not keep(posting(locations=("Anywhere",)), scope=scope)
    assert keep(posting(locations=("Remote - Portugal",)), scope=scope)


def test_on_site_work_needs_an_intent_that_accepts_it() -> None:
    scope = LocationScope(frozenset({"PT"}), include_worldwide=True)
    assert not keep(posting(locations=("Lisbon",)), scope=scope)
    assert keep(posting(locations=("Remote - Portugal",)), scope=scope)


def test_without_a_scope_the_location_is_not_filtered() -> None:
    assert keep(posting(locations=("Berlin",)), scope=None)
    assert keep(posting(locations=("Berlin",)), scope=LocationScope())


# --- applying to a list -----------------------------------------------------------------------


def test_apply_filters_counts_what_it_drops_and_respects_the_limit() -> None:
    postings = [
        make_posting("1", title="Backend Engineer", locations=("Remote - EU",)),
        make_posting("2", title="Account Executive", locations=("Remote - EU",)),
        make_posting("3", title="Data Engineer", locations=("Remote - EU",)),
        make_posting("4", title="DevOps Engineer", locations=("Remote - EU",)),
    ]
    outcome = apply_filters(postings, JobBoardFilters(max_postings_per_run=2), SCOPE, NOW)
    assert [p.external_job_id for p in outcome.kept] == ["1", "3"]
    assert outcome.dropped == 1
    assert outcome.truncated is True
    everything = apply_filters(postings, JobBoardFilters(), SCOPE, NOW)
    assert (len(everything.kept), everything.dropped, everything.truncated) == (3, 1, False)
