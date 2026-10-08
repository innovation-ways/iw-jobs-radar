"""Unit tests for the worker heartbeat freshness rule used by /readyz (ADR-031, ADR-036)."""

from datetime import UTC, datetime, timedelta

from jobs_radar.services.readiness import evaluate_worker_heartbeat

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def test_no_heartbeat_means_missing() -> None:
    assert evaluate_worker_heartbeat(None, NOW, max_age_seconds=60).value == "missing"


def test_recent_heartbeat_is_up() -> None:
    assert evaluate_worker_heartbeat(NOW - timedelta(seconds=30), NOW, 60).value == "up"


def test_old_heartbeat_is_stale() -> None:
    assert evaluate_worker_heartbeat(NOW - timedelta(seconds=61), NOW, 60).value == "stale"


def test_boundary_is_still_up() -> None:
    assert evaluate_worker_heartbeat(NOW - timedelta(seconds=60), NOW, 60).value == "up"
