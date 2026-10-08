"""Pure trend maths: weeks, openness, shares, change, periods and markers (T7.5, document 13 s.11)."""

from datetime import UTC, date, datetime

from jobs_radar.domain.trends import (
    PERIODS,
    change_between,
    change_points,
    is_open_at,
    period_availability,
    share,
    source_set_hash,
    week_range,
    week_start,
)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_weeks_start_on_monday_utc() -> None:
    assert week_start(utc(2032, 6, 16, 12)) == date(2032, 6, 14)  # Wednesday
    assert week_start(utc(2032, 6, 14, 0, 0)) == date(2032, 6, 14)  # Monday midnight
    assert week_start(utc(2032, 6, 13, 23, 59)) == date(
        2032, 6, 7
    )  # Sunday belongs to the week before


def test_a_range_of_weeks_is_inclusive_and_ordered() -> None:
    assert week_range(date(2032, 5, 31), date(2032, 6, 14)) == [
        date(2032, 5, 31),
        date(2032, 6, 7),
        date(2032, 6, 14),
    ]
    assert week_range(date(2032, 6, 14), date(2032, 6, 14)) == [date(2032, 6, 14)]
    assert week_range(date(2032, 6, 14), date(2032, 6, 7)) == []


def test_an_opportunity_is_open_between_its_first_sight_and_its_closing() -> None:
    first, closed = utc(2032, 6, 1), utc(2032, 6, 10)
    assert not is_open_at(first, None, utc(2032, 5, 31))
    assert is_open_at(first, None, utc(2032, 6, 1))
    assert is_open_at(first, closed, utc(2032, 6, 9, 23))
    assert not is_open_at(first, closed, utc(2032, 6, 10))
    assert is_open_at(first, None, utc(2040, 1, 1))


def test_share_is_a_fraction_and_unknown_without_a_total() -> None:
    assert share(3, 12) == 0.25
    assert share(0, 5) == 0.0
    assert share(1, 0) is None


def test_change_is_measured_between_the_first_and_last_known_value() -> None:
    assert abs((change_between([0.10, 0.12, 0.15]) or 0) - 0.05) < 1e-9
    assert abs((change_between([None, 0.2, 0.3]) or 0) - 0.1) < 1e-9
    assert change_between([0.4]) == 0.0
    assert change_between([]) == 0.0
    assert change_between([None, None]) is None


def test_a_period_unlocks_only_when_enough_history_exists() -> None:
    assert [p.weeks for p in PERIODS] == [4, 12, 26]
    assert [(p.key, p.available) for p in period_availability(3)] == [
        ("4w", False),
        ("12w", False),
        ("6m", False),
    ]
    assert [(p.key, p.available) for p in period_availability(4)] == [
        ("4w", True),
        ("12w", False),
        ("6m", False),
    ]
    assert [(p.key, p.available) for p in period_availability(26)] == [
        ("4w", True),
        ("12w", True),
        ("6m", True),
    ]


def test_change_points_mark_where_a_value_differs_from_the_week_before() -> None:
    weeks = [
        (date(2032, 6, 1), "a"),
        (date(2032, 6, 8), "a"),
        (date(2032, 6, 15), "b"),
        (date(2032, 6, 22), "b"),
        (date(2032, 6, 29), "a"),
    ]
    assert change_points(weeks) == [date(2032, 6, 15), date(2032, 6, 29)]
    assert change_points([]) == [] and change_points([(date(2032, 6, 1), "x")]) == []


def test_the_source_set_hash_is_order_independent_and_changes_with_the_set() -> None:
    assert source_set_hash([3, 1, 2]) == source_set_hash([1, 2, 3])
    assert source_set_hash([1, 2]) != source_set_hash([1, 2, 3])
    assert len(source_set_hash([])) == 64
