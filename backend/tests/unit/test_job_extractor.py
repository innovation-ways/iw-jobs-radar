"""The extractor: provider call, validation, one repair, evidence and key checks (T4.2)."""

import json
from typing import Any

import pytest
from tests.data import SAMPLE_JOB_DESCRIPTION, SAMPLE_JOB_TITLE, sample_extraction_output
from tests.fake_provider import FakeProvider

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.domain.enums import ProviderErrorClass
from jobs_radar.services.extraction import ExtractionError, ExtractionInput, JobExtractor

TAXONOMY = {
    "role_family": {"ai_solutions_engineering"},
    "sector": {"enterprise_it"},
    "seniority_level": {"senior"},
    "engagement_type": {"contractor_b2b"},
    "employer_type": {"direct_employer"},
    "benefit": {"flexible_hours"},
}


def extractor(provider: FakeProvider, max_chars: int = 12000) -> JobExtractor:
    return JobExtractor(provider, TAXONOMY, max_chars=max_chars)


def job(**changes: Any) -> ExtractionInput:
    values = {
        "title": SAMPLE_JOB_TITLE,
        "description": SAMPLE_JOB_DESCRIPTION,
        "hints": {"locations": ["Remote - EU"]},
        **changes,
    }
    return ExtractionInput(**values)


async def test_a_valid_answer_is_returned_verified() -> None:
    provider = FakeProvider([sample_extraction_output()])
    result = await extractor(provider).extract(job())
    assert result.output.work_mode.value == "remote"
    assert [s.name for s in result.output.skills] == ["Python", "API design"]
    assert (result.unverified, result.dropped_keys, result.contradictions) == ([], [], [])
    assert (result.truncated, result.latency_ms) == (False, 7)
    assert len(provider.requests) == 1


async def test_invalid_json_gets_exactly_one_repair_with_the_error_and_the_answer() -> None:
    provider = FakeProvider(["this is not json", sample_extraction_output()])
    result = await extractor(provider).extract(job())
    assert result.output.work_mode.value == "remote"
    assert len(provider.requests) == 2
    repair = provider.requests[1].user
    assert "this is not json" in repair and "invalid" in repair.lower()
    assert SAMPLE_JOB_DESCRIPTION in repair  # the repair still carries the posting


async def test_an_answer_that_breaks_the_contract_is_repaired_too() -> None:
    broken = sample_extraction_output()
    broken["work_mode"] = {
        "value": "remote",
        "status": "known",
        "confidence": 0.9,
        "evidence": None,
    }
    provider = FakeProvider([broken, sample_extraction_output()])
    result = await extractor(provider).extract(job())
    assert result.output.work_mode.status == "known"
    assert len(provider.requests) == 2


async def test_two_unusable_answers_fail_and_count_as_an_attempt() -> None:
    provider = FakeProvider(["nope", '{"still": "wrong"}'])
    with pytest.raises(ExtractionError) as error:
        await extractor(provider).extract(job())
    assert error.value.error_class == "invalid_output"
    assert error.value.counts_as_attempt is True
    assert len(provider.requests) == 2  # one repair only, never more


@pytest.mark.parametrize(
    ("provider_error", "counts"),
    [
        (ProviderErrorClass.UNAVAILABLE, False),
        (ProviderErrorClass.MODEL_NOT_FOUND, False),
        (ProviderErrorClass.BLOCKED_URL, False),
        (ProviderErrorClass.HTTP_ERROR, False),
        (ProviderErrorClass.TIMEOUT, True),
        (ProviderErrorClass.INVALID_RESPONSE, True),
    ],
)
async def test_provider_failures_are_classified_and_only_some_use_up_an_attempt(
    provider_error: ProviderErrorClass, counts: bool
) -> None:
    provider = FakeProvider([ProviderError(provider_error, "generic")])
    with pytest.raises(ExtractionError) as error:
        await extractor(provider).extract(job())
    assert error.value.error_class == provider_error.value
    assert error.value.counts_as_attempt is counts
    assert len(provider.requests) == 1


async def test_a_provider_failure_during_the_repair_is_reported_as_such() -> None:
    provider = FakeProvider(["bad", ProviderError(ProviderErrorClass.UNAVAILABLE, "down")])
    with pytest.raises(ExtractionError) as error:
        await extractor(provider).extract(job())
    assert error.value.error_class == "unavailable"


async def test_unverified_evidence_and_unknown_keys_are_reported_not_hidden() -> None:
    answer = sample_extraction_output()
    answer["work_mode"] = {
        "value": "hybrid",
        "status": "known",
        "confidence": 0.9,
        "evidence": "three days in the office",
    }
    answer["role_families"].append(
        {
            "key": "wizardry",
            "confidence": 0.9,
            "evidence": "Design and evaluate LLM-powered features",
        }
    )
    result = await extractor(FakeProvider([answer])).extract(job())
    assert result.output.work_mode.status == "unknown"
    assert result.unverified == ["work_mode"]
    assert result.dropped_keys == ["role_families:wizardry"]


async def test_a_contradiction_with_the_source_is_flagged() -> None:
    result = await extractor(FakeProvider([sample_extraction_output()])).extract(
        job(hints={"locations": ["Berlin, Germany"]})
    )
    assert result.contradictions and result.contradictions[0]["attribute"] == "locations"


async def test_long_descriptions_are_truncated_and_the_quotes_are_checked_against_the_sent_text() -> (
    None
):
    provider = FakeProvider([sample_extraction_output()])
    result = await extractor(provider, max_chars=60).extract(job())
    assert result.truncated is True
    # most quotes are beyond the first 60 characters, so they cannot be verified
    assert "work_mode" in result.unverified
    assert SAMPLE_JOB_DESCRIPTION not in provider.requests[0].user


async def test_the_stored_attributes_carry_the_output_and_the_checks() -> None:
    result = await extractor(FakeProvider([sample_extraction_output()])).extract(job())
    stored = result.stored_attributes()
    assert stored["output"]["work_mode"]["value"] == "remote"
    assert (
        stored["unverified"] == []
        and stored["dropped_keys"] == []
        and stored["contradictions"] == []
    )
    json.dumps(stored)  # JSON-serialisable for the database
