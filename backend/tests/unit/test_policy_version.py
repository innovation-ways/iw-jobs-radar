"""The matching policy version changed with the career-direction dimension of ADR-057."""

from jobs_radar.domain.matching.engine import POLICY_VERSION


def test_the_policy_version_is_the_one_approved_in_adr_057() -> None:
    assert POLICY_VERSION == "matching-v1.5"
