"""Gates G7 to G11 and the rule that a gate never fires on unknown data."""

from tests.unit.matching.builders import gate_codes, intent, job, run


def test_a_required_language_the_owner_does_not_work_in_fires_g7() -> None:
    evaluation = run(job(languages_required=("en", "de")))
    assert gate_codes(evaluation) == ["G7"]
    assert evaluation.gates[0].evidence["missing"] == ["de"]


def test_g7_needs_the_flag_and_known_languages() -> None:
    assert (
        gate_codes(run(job(languages_required=("de",)), intent(reject_unspoken_required=False)))
        == []
    )
    assert gate_codes(run(job(languages_required=("en", "pt")))) == []
    assert gate_codes(run(job())) == []  # unknown languages never gate


def test_an_ignored_company_fires_g8_ignoring_case_and_spacing() -> None:
    evaluation = run(
        job(company_name="  harbor   SYSTEMS "), intent(excluded_companies=("Harbor Systems",))
    )
    assert gate_codes(evaluation) == ["G8"]
    assert (
        gate_codes(run(job(company_name="Acme"), intent(excluded_companies=("Harbor Systems",))))
        == []
    )


def test_an_excluded_word_fires_g9_only_as_a_whole_word_in_the_title_or_description() -> None:
    words = intent(excluded_words=("unpaid", "sales quota"))
    assert gate_codes(run(job(description="This is an UNPAID internship."), words)) == ["G9"]
    assert gate_codes(run(job(title="Unpaid Engineer"), words)) == ["G9"]
    assert gate_codes(run(job(description="Meet your sales quota monthly."), words)) == ["G9"]
    assert (
        gate_codes(run(job(description="Fully repaid relocation."), words)) == []
    )  # not a whole word
    assert gate_codes(run(job(description="Nothing to see."), words)) == []


def test_needing_visa_help_when_the_posting_says_it_is_not_offered_fires_g11() -> None:
    needs = intent(needs_visa=True)
    assert gate_codes(run(job(visa_sponsorship=False), needs)) == ["G11"]
    assert gate_codes(run(job(visa_sponsorship=True), needs)) == []
    assert gate_codes(run(job(visa_sponsorship=None), needs)) == []  # unknown never gates
    assert gate_codes(run(job(visa_sponsorship=False))) == []  # the owner does not need it


def test_every_fired_gate_is_listed_with_its_reason_and_the_recommendation_follows() -> None:
    evaluation = run(
        job(description="unpaid", languages_required=("de",), company_name="Harbor Systems"),
        intent(excluded_words=("unpaid",), excluded_companies=("Harbor Systems",)),
    )
    assert gate_codes(evaluation) == ["G7", "G8", "G9"]
    assert all(g.reason for g in evaluation.gates)
    assert evaluation.recommendation == "not_recommended"


def test_nothing_fires_when_everything_is_unknown() -> None:
    evaluation = run(job())
    assert evaluation.gates == () and evaluation.recommendation == "recommended"
