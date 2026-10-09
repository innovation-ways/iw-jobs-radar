"""The pure rules behind the pipeline status: overall state, rate and time left."""

import pytest

from jobs_radar.services.pipeline import estimate_minutes_left, pipeline_state

BASE = {"worker": "up", "ai_configured": True, "waiting": 5, "progressed": True}


def test_without_a_job_analysis_connection_the_state_is_no_ai() -> None:
    assert pipeline_state(**{**BASE, "ai_configured": False}) == "no_ai"


@pytest.mark.parametrize("worker", ["stale", "missing"])
def test_a_worker_that_does_not_report_is_stopped_whatever_else_is_true(worker: str) -> None:
    assert pipeline_state(**{**BASE, "worker": worker}) == "worker_stopped"
    assert pipeline_state(**{**BASE, "worker": worker, "ai_configured": False}) == "worker_stopped"


def test_nothing_waiting_is_idle() -> None:
    assert pipeline_state(**{**BASE, "waiting": 0, "progressed": False}) == "idle"


def test_work_waiting_with_recent_progress_is_working() -> None:
    assert pipeline_state(**BASE) == "working"


def test_work_waiting_without_recent_progress_is_flagged() -> None:
    assert pipeline_state(**{**BASE, "progressed": False}) == "no_progress"


def test_the_time_left_is_the_waiting_jobs_over_the_recent_rate() -> None:
    assert estimate_minutes_left(waiting=440, completed=45, window_minutes=15) == 147
    assert estimate_minutes_left(waiting=1, completed=60, window_minutes=15) == 1  # rounds up


def test_there_is_no_estimate_without_a_rate_or_without_work() -> None:
    assert estimate_minutes_left(waiting=10, completed=0, window_minutes=15) is None
    assert estimate_minutes_left(waiting=0, completed=30, window_minutes=15) is None
