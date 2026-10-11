"""Jobs with far offices and no remote statement are blocked by gate G2 (ADR-058)."""

from tests.unit.matching.builders import BERLIN, LISBON, SETUBAL, dim, gate_codes, job, run

from jobs_radar.domain.matching.types import JobLocation

SAN_FRANCISCO = JobLocation("San Francisco, CA", 37.77493, -122.41942)
NEW_YORK = JobLocation("New York City, NY", 40.71427, -74.00597)


def test_far_offices_with_no_remote_statement_fire_g2() -> None:
    evaluation = run(job(locations=(SAN_FRANCISCO, NEW_YORK)))
    assert gate_codes(evaluation) == ["G2"]
    assert evaluation.recommendation == "not_recommended"
    assert "remotely" in evaluation.gates[0].reason
    result = dim(evaluation, "work_arrangement_location")
    assert result.status == "unknown" and result.contribution == 0


def test_one_office_inside_the_distance_is_not_blocked() -> None:
    assert gate_codes(run(job(locations=(SAN_FRANCISCO, LISBON)))) == []
    assert gate_codes(run(job(locations=(SETUBAL,)))) == []


def test_an_unplaced_office_is_not_blocked() -> None:
    assert gate_codes(run(job(locations=(JobLocation("Somewhere", None, None), BERLIN)))) == []


def test_no_locations_is_not_blocked() -> None:
    assert gate_codes(run(job())) == []


def test_a_stated_arrangement_is_never_touched_by_this_rule() -> None:
    far = job(work_mode="remote", remote_regions=("EU",), locations=(SAN_FRANCISCO,))
    assert gate_codes(run(far)) == []
