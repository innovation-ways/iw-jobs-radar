"""Next and latest scheduled run, across daylight-saving changes and time zones (T5.2)."""

from datetime import UTC, datetime, time

import pytest

from jobs_radar.domain.schedule import (
    latest_occurrence,
    next_occurrence,
    normalise_run_times,
    validate_timezone,
)

LISBON = "Europe/Lisbon"
T0730 = (time(7, 30),)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_the_next_run_is_today_when_the_time_has_not_passed() -> None:
    # 2026-10-08 is summer time in Lisbon (UTC+1): 07:30 local = 06:30 UTC
    assert next_occurrence(utc(2026, 10, 8, 5, 0), T0730, LISBON) == utc(2026, 10, 8, 6, 30)


def test_the_next_run_is_tomorrow_once_the_time_has_passed_and_at_the_exact_time() -> None:
    assert next_occurrence(utc(2026, 10, 8, 6, 31), T0730, LISBON) == utc(2026, 10, 9, 6, 30)
    assert next_occurrence(utc(2026, 10, 8, 6, 30), T0730, LISBON) == utc(2026, 10, 9, 6, 30)


def test_the_local_time_stays_the_same_when_the_clocks_change_back() -> None:
    # Lisbon leaves summer time on 2026-10-25: 07:30 local is 06:30 UTC before, 07:30 UTC after
    assert next_occurrence(utc(2026, 10, 24, 7, 0), T0730, LISBON) == utc(2026, 10, 25, 7, 30)
    assert next_occurrence(utc(2026, 10, 24, 6, 0), T0730, LISBON) == utc(2026, 10, 24, 6, 30)


def test_the_local_time_stays_the_same_when_the_clocks_go_forward() -> None:
    # Lisbon enters summer time on 2027-03-28
    assert next_occurrence(utc(2027, 3, 27, 8, 0), T0730, LISBON) == utc(2027, 3, 28, 6, 30)


def test_a_time_that_does_not_exist_that_day_runs_just_after_the_gap() -> None:
    # 01:30 does not exist in Lisbon on 2027-03-28 (01:00 jumps to 02:00): run at 02:30 local
    assert next_occurrence(utc(2027, 3, 28, 0, 0), (time(1, 30),), LISBON) == utc(
        2027, 3, 28, 1, 30
    )


def test_a_time_that_happens_twice_that_day_runs_the_first_time_only() -> None:
    # 01:30 happens twice in Lisbon on 2026-10-25; the first one is 00:30 UTC
    assert next_occurrence(utc(2026, 10, 24, 12, 0), (time(1, 30),), LISBON) == utc(
        2026, 10, 25, 0, 30
    )
    assert next_occurrence(utc(2026, 10, 25, 0, 31), (time(1, 30),), LISBON) == utc(
        2026, 10, 26, 1, 30
    )


def test_another_time_zone_changes_the_instant() -> None:
    assert next_occurrence(utc(2026, 1, 15, 0, 0), T0730, "America/New_York") == utc(
        2026, 1, 15, 12, 30
    )
    assert next_occurrence(utc(2026, 1, 15, 0, 0), T0730, "UTC") == utc(2026, 1, 15, 7, 30)


def test_changing_the_time_zone_moves_the_next_run() -> None:
    now = utc(2026, 10, 8, 5, 0)
    assert next_occurrence(now, T0730, LISBON) != next_occurrence(now, T0730, "Asia/Tokyo")


def test_the_latest_run_is_the_last_one_not_after_the_given_time() -> None:
    assert latest_occurrence(utc(2026, 10, 8, 9, 0), T0730, LISBON) == utc(2026, 10, 8, 6, 30)
    assert latest_occurrence(utc(2026, 10, 8, 6, 29), T0730, LISBON) == utc(2026, 10, 7, 6, 30)
    assert latest_occurrence(utc(2026, 10, 8, 6, 30), T0730, LISBON) == utc(2026, 10, 8, 6, 30)


@pytest.mark.parametrize("zone", [LISBON, "UTC", "Asia/Kolkata", "America/St_Johns"])
def test_next_and_latest_agree_with_each_other(zone: str) -> None:
    now = utc(2026, 6, 1, 12, 0)
    following = next_occurrence(now, T0730, zone)
    assert following > now
    assert latest_occurrence(following, T0730, zone) == following
    assert latest_occurrence(now, T0730, zone) < now or latest_occurrence(now, T0730, zone) <= now


def test_time_zones_are_validated() -> None:
    assert validate_timezone("Europe/Lisbon") == "Europe/Lisbon"
    for bad in ("Mars/Phobos", "", "lisbon", "../etc/passwd"):
        with pytest.raises(ValueError, match="time zone"):
            validate_timezone(bad)


def test_naive_times_are_rejected() -> None:
    with pytest.raises(ValueError, match="aware"):
        next_occurrence(datetime(2026, 10, 8, 5, 0), T0730, LISBON)


# Several times a day (ADR-062): 09:00, 12:00 and 16:00 Lisbon summer time = 08:00, 11:00, 15:00 UTC
THREE = (time(9, 0), time(12, 0), time(16, 0))


def test_the_next_run_is_the_nearest_time_of_the_day() -> None:
    assert next_occurrence(utc(2026, 10, 8, 7, 0), THREE, LISBON) == utc(2026, 10, 8, 8, 0)
    assert next_occurrence(utc(2026, 10, 8, 8, 0), THREE, LISBON) == utc(2026, 10, 8, 11, 0)
    assert next_occurrence(utc(2026, 10, 8, 12, 0), THREE, LISBON) == utc(2026, 10, 8, 15, 0)


def test_after_the_last_time_the_next_run_is_the_first_one_tomorrow() -> None:
    assert next_occurrence(utc(2026, 10, 8, 15, 0), THREE, LISBON) == utc(2026, 10, 9, 8, 0)


def test_the_order_of_the_times_does_not_matter() -> None:
    shuffled = (time(16, 0), time(9, 0), time(12, 0))
    now = utc(2026, 10, 8, 9, 0)
    assert next_occurrence(now, shuffled, LISBON) == next_occurrence(now, THREE, LISBON)
    assert latest_occurrence(now, shuffled, LISBON) == latest_occurrence(now, THREE, LISBON)


def test_the_latest_run_is_the_most_recent_time_that_has_passed() -> None:
    assert latest_occurrence(utc(2026, 10, 8, 13, 0), THREE, LISBON) == utc(2026, 10, 8, 11, 0)
    assert latest_occurrence(utc(2026, 10, 8, 23, 0), THREE, LISBON) == utc(2026, 10, 8, 15, 0)
    # before the first time of the day, the last time of the previous day
    assert latest_occurrence(utc(2026, 10, 8, 7, 0), THREE, LISBON) == utc(2026, 10, 7, 15, 0)


def test_no_times_is_an_error() -> None:
    with pytest.raises(ValueError, match="at least one"):
        next_occurrence(utc(2026, 10, 8, 7, 0), (), LISBON)
    with pytest.raises(ValueError, match="at least one"):
        latest_occurrence(utc(2026, 10, 8, 7, 0), (), LISBON)


def test_normalise_run_times_sorts_drops_seconds_and_duplicates() -> None:
    assert normalise_run_times([time(16, 0, 30), time(9, 0), time(9, 0, 10), time(12, 0)]) == THREE
    with pytest.raises(ValueError, match="at least one"):
        normalise_run_times([])
    with pytest.raises(ValueError, match="at most"):
        normalise_run_times([time(hour, 0) for hour in range(13)])
