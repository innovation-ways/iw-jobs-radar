"""Region groups for remote eligibility (document 13, section 7.4)."""

import pytest

from jobs_radar.domain.regions import regions_intersect


@pytest.mark.parametrize(
    ("job", "user", "expected"),
    [
        (["EU"], ["EU"], True),
        (["PT"], ["EU"], True),  # Portugal is in the EU
        (["EU"], ["PT"], True),  # a job open to the EU is open to someone in Portugal
        (["US"], ["EU"], False),
        (["EU"], ["UK"], False),  # the UK left the EU
        (["UK"], ["GB"], True),  # UK and GB are the same
        (["United Kingdom"], ["UK"], True),
        (["EEA"], ["NO"], True),
        (["EU"], ["NO"], False),
        (["EUROPE"], ["UK"], True),
        (["Europe"], ["PT"], True),
        (["WORLD"], ["PT"], True),
        (["worldwide"], ["EU"], True),
        (["anywhere"], ["US"], True),
        (["PT", "ES"], ["FR"], False),
        (["PT", "ES"], ["FR", "ES"], True),
        (["eu", " pt "], ["EU"], True),  # case and spacing do not matter
    ],
)
def test_regions_intersect(job: list[str], user: list[str], expected: bool) -> None:
    assert regions_intersect(job, user) is expected


def test_unrecognised_job_regions_cannot_be_judged() -> None:
    assert regions_intersect(["Atlantis"], ["EU"]) is None
    assert regions_intersect([], ["EU"]) is None


def test_recognised_and_unrecognised_tokens_together_use_the_recognised_ones() -> None:
    assert regions_intersect(["Atlantis", "PT"], ["EU"]) is True
    assert regions_intersect(["Atlantis", "US"], ["EU"]) is False


def test_an_empty_user_list_never_intersects() -> None:
    assert regions_intersect(["EU"], []) is False
