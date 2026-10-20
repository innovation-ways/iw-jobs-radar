"""Mapping stored extractions, profiles and intents to the engine's inputs."""

from decimal import Decimal

from tests.data import (
    SAMPLE_JOB_DESCRIPTION,
    SAMPLE_JOB_TITLE,
    sample_extraction_output,
    sample_intent,
    sample_profile_facts,
)
from tests.golden import golden_optional_terms

from jobs_radar.schemas.intent import IntentDefinition
from jobs_radar.schemas.profile import ProfileFacts
from jobs_radar.services.evaluation_inputs import intent_view, job_attributes, profile_view


def stored(**changes: object) -> dict[str, object]:
    return {
        "output": sample_extraction_output(),
        "unverified": [],
        "dropped_keys": [],
        "contradictions": [],
        "skills_resolved": [
            {"skill_id": 17, "name": "Python", "importance": "must"},
            {"skill_id": 18, "name": "API design", "importance": "nice"},
        ],
        "locations_resolved": [
            {
                "raw": "Lisbon, Portugal",
                "resolved": True,
                "city": "Lisbon",
                "country": "PT",
                "latitude": 38.7,
                "longitude": -9.1,
                "timezone": "Europe/Lisbon",
            },
            {"raw": "Remote - EU", "resolved": False},
        ],
        **changes,
    }


def test_a_stored_extraction_becomes_job_attributes() -> None:
    job = job_attributes(stored(), SAMPLE_JOB_TITLE, SAMPLE_JOB_DESCRIPTION, "Acme")
    assert (job.title, job.description, job.company_name) == (
        SAMPLE_JOB_TITLE,
        SAMPLE_JOB_DESCRIPTION,
        "Acme",
    )
    assert job.role_families == (("ai_solutions_engineering", 0.93),)
    assert (job.work_mode, job.remote_regions) == ("remote", ("EU",))
    assert job.employment_types == ("contractor_b2b",) and job.hours is None
    assert job.seniority_levels == ("senior",) and job.sector_primary == "enterprise_it"
    assert job.employer_type == "direct_employer" and job.languages_required == ("en",)
    assert job.benefits_mentioned == ("flexible_hours",)
    assert job.pay is None and job.visa_sponsorship is None and job.education_required is None
    assert [(s.skill_id, s.importance) for s in job.skills] == [(17, "must"), (18, "nice")]


def test_resolved_locations_carry_coordinates_and_unresolved_ones_do_not() -> None:
    job = job_attributes(stored(), "t", "d", "Acme")
    assert [(loc.raw, loc.latitude, loc.longitude) for loc in job.locations] == [
        ("Lisbon, Portugal", 38.7, -9.1),
        ("Remote - EU", None, None),
    ]


def test_evidence_quotes_are_carried_for_the_results() -> None:
    job = job_attributes(stored(), SAMPLE_JOB_TITLE, SAMPLE_JOB_DESCRIPTION, "Acme")
    assert job.evidence["work_mode"] == "Fully remote within EU time zones."
    assert job.evidence["role_families"] == "Design and evaluate LLM-powered features"
    assert "compensation" not in job.evidence  # unknown attributes have no quote


def test_stated_pay_is_mapped_as_stated() -> None:
    output = sample_extraction_output()
    output["compensation"] = {
        "value": {
            "form": "day_rate",
            "currency": "EUR",
            "min": 500,
            "max": 600,
            "period": "day",
            "disclosed": True,
        },
        "status": "known",
        "confidence": 0.9,
        "evidence": "500 to 600 EUR per day",
    }
    job = job_attributes(stored(output=output), "t", "d", "Acme")
    assert job.pay is not None and (
        job.pay.form,
        job.pay.minimum,
        job.pay.maximum,
        job.pay.period,
    ) == ("day_rate", 500, 600, "day")


def test_a_profile_becomes_skill_levels_languages_and_education() -> None:
    view = profile_view(ProfileFacts.model_validate(sample_profile_facts()))
    assert view.skill_levels == {17: "expert", 18: "advanced"}
    assert view.languages == frozenset({"pt", "en"})
    assert view.education_levels == ("msc",) and view.certifications == ("Example Certification",)


def test_an_intent_becomes_stances_rules_pay_and_weights() -> None:
    view = intent_view(IntentDefinition.model_validate(sample_intent()), {})
    assert view.stances["role_families"]["ai_solutions_engineering"] == "preferred"
    assert view.stances["work_arrangements"]["remote"] == "preferred"
    assert view.part_time == "rejected"
    assert view.remote_regions == ("EU", "UK")
    assert (view.base_latitude, view.base_longitude, view.radius_km) == (38.72, -9.14, 40)
    assert view.employee_pay is not None
    assert (
        view.employee_pay.currency,
        view.employee_pay.minimum,
        view.employee_pay.target,
        view.employee_pay.payments_per_year,
    ) == ("EUR", 60000, 75000, 14)
    assert view.contractor_pay is not None and (
        view.contractor_pay.minimum,
        view.contractor_pay.target,
    ) == (450, 550)
    assert view.can_work_in == frozenset({"pt", "en"}) and view.reject_unspoken_required is True
    assert view.weights["compensation"] == 10 and view.weights["qualifications"] == 0
    assert Decimal(view.weights["role_responsibilities"]) == 25


def stored_regions(regions: list[str]) -> dict[str, object]:
    output = sample_extraction_output()
    output["remote_regions"] = {
        "value": regions,
        "status": "known",
        "confidence": 0.9,
        "evidence": "within EU time zones",
    }
    return stored(output=output)


def test_regions_named_as_countries_are_turned_into_codes_the_engine_understands() -> None:
    job = job_attributes(stored_regions(["Austria", "Portugal", "EU", "uk"]), "T", "D", "Acme")
    # Names become ISO codes; groups and codes are left for the engine (ADR-052).
    assert job.remote_regions == ("AT", "PT", "EU", "uk")


def test_a_region_that_is_not_a_country_is_kept_as_written() -> None:
    job = job_attributes(stored_regions(["EMEA", "Worldwide"]), "T", "D", "Acme")
    assert job.remote_regions == ("EMEA", "Worldwide")


def test_a_job_open_only_to_austria_is_a_mismatch_for_an_owner_in_portugal() -> None:
    from jobs_radar.domain.regions import regions_intersect

    job = job_attributes(stored_regions(["Austria"]), "T", "D", "Acme")
    assert regions_intersect(job.remote_regions or (), ("PT",)) is False


# --- the source's own remote place limits the regions the model reports (ADR-056) --------------


def narrowed(regions: list[str] | None, places: list[str]) -> tuple[str, ...] | None:
    """Regions of a job whose model answer is ``regions`` and whose source says ``places``."""
    attributes = stored_regions(regions) if regions is not None else stored()
    if regions is None:
        output = sample_extraction_output()
        output["remote_regions"] = {
            "value": None,
            "status": "unknown",
            "confidence": 0.0,
            "evidence": None,
        }
        attributes = stored(output=output)
    job = job_attributes(attributes, "t", "d", "Acme", source_places=places)
    return job.remote_regions


def test_a_remote_place_in_one_country_narrows_a_worldwide_answer() -> None:
    assert narrowed(["WORLD"], ["India (Remote)"]) == ("IN",)


def test_an_answer_that_shares_nothing_with_the_source_becomes_the_sources_countries() -> None:
    # The model said EU from a sentence about business hours, the source says Remote US: no region
    # of the owner's is left, so the gate applies.
    assert narrowed(["EU"], ["Remote US", "Remote"]) == ("US",)


def test_only_the_shared_countries_are_kept() -> None:
    assert narrowed(["EU", "UK"], ["Remote - Germany", "Remote - India"]) == ("DE",)


def test_an_answer_inside_the_source_limit_is_left_as_the_model_wrote_it() -> None:
    assert narrowed(["EU"], ["Remote, Europe"]) == ("EU",)


def test_a_source_that_limits_nothing_changes_nothing() -> None:
    assert narrowed(["WORLD"], ["Seattle", "Remote"]) == ("WORLD",)
    assert narrowed(["EU"], []) == ("EU",)


def test_regions_the_model_did_not_state_use_the_sources_countries_for_remote_work() -> None:
    # ADR-058: the model said nothing about regions, the source says Remote USA: the job is open
    # from the US only, so gate G2 can apply instead of "regions not stated, a risk".
    assert narrowed(None, ["Remote - USA"]) == ("US",)
    assert narrowed(None, ["India (Remote)"]) == ("IN",)


def test_unstated_regions_stay_unknown_when_the_source_limits_nothing() -> None:
    assert narrowed(None, ["Seattle", "Remote"]) is None
    assert narrowed(None, []) is None
    assert narrowed(None, ["Remote - Worldwide"]) is None


def test_unstated_regions_are_left_alone_when_the_job_is_not_remote() -> None:
    output = sample_extraction_output()
    output["work_mode"] = {"value": "hybrid", "status": "known", "confidence": 0.9, "evidence": "x"}
    output["remote_regions"] = {
        "value": None,
        "status": "unknown",
        "confidence": 0.0,
        "evidence": None,
    }
    job = job_attributes(stored(output=output), "t", "d", "Acme", source_places=["Remote - USA"])
    assert job.remote_regions is None


def test_the_quote_says_the_source_gave_the_regions_when_the_model_gave_none() -> None:
    output = sample_extraction_output()
    output["remote_regions"] = {
        "value": None,
        "status": "unknown",
        "confidence": 0.0,
        "evidence": None,
    }
    job = job_attributes(stored(output=output), "t", "d", "Acme", source_places=["Remote - USA"])
    assert "Remote - USA" in job.evidence["remote_regions"]


def test_the_quote_says_the_source_limited_the_regions() -> None:
    job = job_attributes(
        stored_regions(["WORLD"]), "t", "d", "Acme", source_places=["India (Remote)"]
    )
    assert "within EU time zones" in job.evidence["remote_regions"]
    assert "India (Remote)" in job.evidence["remote_regions"]
    unchanged = job_attributes(stored_regions(["EU"]), "t", "d", "Acme", source_places=[])
    assert unchanged.evidence["remote_regions"] == "within EU time zones"


# --- the evidence shows where each region came from (ADR-069) ----------------------------------


def test_the_job_keeps_the_sources_places_and_the_regions_the_text_gave() -> None:
    job = job_attributes(
        stored_regions(["US", "Europe"]),
        "t",
        "d",
        "Acme",
        source_places=["North America", "Remote"],
    )
    assert job.source_places == ("North America", "Remote")
    assert job.text_remote_regions == ("US", "Europe")  # as the model wrote them
    assert job.remote_regions == ("US",)  # what the source left of them


def test_without_source_places_the_job_carries_none() -> None:
    job = job_attributes(stored_regions(["EU"]), "t", "d", "Acme", source_places=[])
    assert job.source_places == ()
    assert job.text_remote_regions == ("EU",)


def test_a_term_the_intent_does_not_list_is_acceptable_when_it_was_added_after_version_one() -> (
    None
):
    """ADR-073: an older intent has no stance for ``contractor_agency``; the form shows it as OK."""
    definition = IntentDefinition.model_validate(sample_intent())
    assert "contractor_agency" not in {e.key for e in definition.stances.engagement_types}
    view = intent_view(definition, golden_optional_terms())
    assert view.stances["engagement_types"]["contractor_agency"] == "acceptable"
    # A stance the owner did set is never overridden.
    assert view.stances["engagement_types"]["contractor_b2b"] == "preferred"
