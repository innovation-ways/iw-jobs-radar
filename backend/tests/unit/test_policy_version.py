"""The matching policy version changed with the input fix of ADR-052."""

from jobs_radar.domain.matching.engine import POLICY_VERSION


def test_the_policy_version_is_the_one_approved_in_adr_052() -> None:
    assert POLICY_VERSION == "matching-v1.1"
