"""Licences and certifications: the qualifications dimension and gate G12 (ADR-080, phase 6a)."""

from decimal import Decimal
from typing import Any

from tests.unit.matching.builders import DEFAULT_WEIGHTS, dim, gate_codes, intent, job, profile, run

from jobs_radar.domain.matching.types import DimensionResult, JobAttributes, JobSkill, ProfileView

LICENCE = JobSkill(501, "Driving licence (category B)", "must")
FORKLIFT = JobSkill(502, "Forklift operator licence", "nice")
WEIGHTS = {**DEFAULT_WEIGHTS, "qualifications": 10}


def qualifications(
    the_job: JobAttributes, the_profile: ProfileView | None = None, **intent_changes: Any
) -> DimensionResult:
    changes = {"weights": WEIGHTS, **intent_changes}
    return dim(run(the_job, intent(**changes), the_profile or profile()), "qualifications")


def holding(*skill_ids: int) -> ProfileView:
    return profile(credential_ids=frozenset(skill_ids))


def test_without_credentials_the_dimension_is_what_it_was() -> None:
    assert qualifications(job()).status == "unknown"
    met = qualifications(job(education_required="msc"))
    assert (met.status, met.strength) == ("match", Decimal("1.0000"))


def test_a_held_credential_is_a_full_match_and_the_evidence_says_so() -> None:
    result = qualifications(job(credentials=(LICENCE,)), holding(501))
    assert (result.status, result.quality, result.strength) == (
        "match",
        "strong",
        Decimal("1.0000"),
    )
    assert result.evidence["credentials"] == [
        {"name": "Driving licence (category B)", "importance": "must", "held": True}
    ]


def test_a_must_counts_twice_and_a_nice_once() -> None:
    both = job(credentials=(LICENCE, FORKLIFT))
    assert qualifications(both, holding(501)).strength == Decimal("0.6667")  # 2 of 3
    assert qualifications(both, holding(502)).strength == Decimal("0.3333")  # 1 of 3
    assert qualifications(both, holding(501, 502)).strength == Decimal("1.0000")


def test_holding_none_is_a_mismatch_but_not_a_gate() -> None:
    result = run(job(credentials=(LICENCE,)), intent(weights=WEIGHTS), holding())
    owned = dim(result, "qualifications")
    assert (owned.status, owned.strength) == ("mismatch", Decimal("0.0000"))
    assert gate_codes(result) == []


def test_a_held_licence_does_not_count_as_a_skill() -> None:
    """Credentials are not technologies: they never enter the skills dimension."""
    result = run(job(credentials=(LICENCE,)), intent(), holding(501))
    assert dim(result, "skills_technology").status == "unknown"


def test_education_and_credentials_are_averaged_when_both_are_known() -> None:
    both = job(education_required="msc", credentials=(LICENCE,))
    assert qualifications(both, holding()).strength == Decimal("0.5000")  # 1.0 and 0.0
    assert qualifications(both, holding(501)).strength == Decimal("1.0000")
    below = profile(education_levels=(), credential_ids=frozenset({501}))
    assert qualifications(both, below).strength == Decimal("0.5000")


def test_the_credentials_alone_decide_when_the_posting_states_no_education() -> None:
    assert qualifications(job(credentials=(FORKLIFT,)), holding(502)).strength == Decimal("1.0000")


# --- gate G12 ------------------------------------------------------------------------------------------------


def test_the_gate_is_off_unless_the_owner_asks_for_it() -> None:
    assert gate_codes(run(job(credentials=(LICENCE,)), intent(), holding())) == []


def test_a_missing_must_have_credential_fires_g12_when_asked() -> None:
    result = run(
        job(credentials=(LICENCE, FORKLIFT), evidence={"credentials": "a valid licence"}),
        intent(reject_missing_credentials=True),
        holding(502),
    )
    assert gate_codes(result) == ["G12"]
    (gate,) = result.gates
    assert gate.evidence["missing"] == ["Driving licence (category B)"]
    assert gate.evidence["job_quote"] == "a valid licence"
    assert result.recommendation == "not_recommended"


def test_a_missing_nice_to_have_never_fires_the_gate() -> None:
    result = run(job(credentials=(FORKLIFT,)), intent(reject_missing_credentials=True), holding())
    assert gate_codes(result) == []


def test_holding_every_required_credential_passes() -> None:
    result = run(job(credentials=(LICENCE,)), intent(reject_missing_credentials=True), holding(501))
    assert gate_codes(result) == []


def test_a_job_with_no_known_credentials_is_never_gated() -> None:
    """A gate never fires on unknown data."""
    assert gate_codes(run(job(), intent(reject_missing_credentials=True), holding())) == []


def test_the_gate_works_even_when_the_dimension_has_no_weight() -> None:
    result = run(job(credentials=(LICENCE,)), intent(reject_missing_credentials=True), holding())
    assert dim(result, "qualifications").excluded is True
    assert gate_codes(result) == ["G12"]
