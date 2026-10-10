"""The direction judge: prompt, answer checks and failures (ADR-057, prompt direction-v1)."""

import json

import pytest
from tests.fake_provider import FakeProvider

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.domain.enums import DIRECTION_PROMPT_VERSION, ProviderErrorClass
from jobs_radar.services.direction_judge import DirectionError, DirectionJudge, DirectionTarget

TARGET = DirectionTarget(
    label="Billing SME",
    text="I work as a billing SME and look for telecom roles that fit my skills.",
)
TITLE = "Senior Billing Analyst"
DESCRIPTION = (
    "You will own the convergent billing platform of a large telecom operator.\n"
    "Requirements: five years of rating and charging experience."
)


def answer(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "level": "strong",
        "job_quote": "convergent billing platform of a large telecom operator",
        "direction_quote": "billing SME",
    }
    return {**base, **changes}


async def judge(*script: object, **kwargs: object):  # type: ignore[no-untyped-def]
    provider = FakeProvider(list(script))
    judge_ = DirectionJudge(provider, max_chars=12000)
    return await judge_.judge(TARGET, title=TITLE, description=DESCRIPTION), provider


async def test_a_verified_answer_is_kept() -> None:
    result, _ = await judge(answer())
    assert (result.level, result.job_quote, result.direction_quote) == (
        "strong",
        "convergent billing platform of a large telecom operator",
        "billing SME",
    )


async def test_the_prompt_has_the_direction_and_the_job_and_nothing_about_the_profile() -> None:
    _, provider = await judge(answer())
    request = provider.requests[0]
    assert TARGET.text in request.user and TITLE in request.user and DESCRIPTION in request.user
    assert "Billing SME" in request.user
    assert set(request.json_schema["properties"]) == {"level", "job_quote", "direction_quote"}
    assert set(request.json_schema["properties"]["level"]["enum"]) == {
        "strong",
        "partial",
        "weak",
        "none",
        "unknown",
    }
    assert DIRECTION_PROMPT_VERSION == "direction-v1"


@pytest.mark.parametrize("level", ["strong", "partial", "weak"])
async def test_a_fit_whose_job_quote_is_not_in_the_posting_becomes_unknown(level: str) -> None:
    result, _ = await judge(answer(level=level, job_quote="a sentence the posting never says"))
    assert (result.level, result.job_quote, result.direction_quote) == ("unknown", None, None)


async def test_a_quote_of_the_direction_that_is_not_in_the_text_is_dropped_but_the_level_stays() -> (
    None
):
    result, _ = await judge(answer(direction_quote="something I never wrote"))
    assert (result.level, result.direction_quote) == ("strong", None)
    assert result.job_quote is not None


async def test_none_and_unknown_need_no_quote() -> None:
    none, _ = await judge({"level": "none", "job_quote": None, "direction_quote": None})
    unknown, _ = await judge({"level": "unknown"})
    assert (none.level, unknown.level) == ("none", "unknown")


async def test_quotes_are_checked_after_normalising_case_and_spacing() -> None:
    result, _ = await judge(answer(job_quote="CONVERGENT   billing platform"))
    assert result.level == "strong"


async def test_an_invalid_level_is_repaired_once() -> None:
    result, provider = await judge("not json at all", answer())
    assert result.level == "strong" and len(provider.requests) == 2
    assert "invalid" in provider.requests[1].user.lower()


async def test_an_answer_that_stays_invalid_fails_and_stores_nothing() -> None:
    with pytest.raises(DirectionError) as caught:
        await judge("nope", json.dumps({"level": "amazing"}))
    assert caught.value.counts_as_attempt is True


@pytest.mark.parametrize(
    ("error_class", "infrastructure"),
    [
        (ProviderErrorClass.UNAVAILABLE, True),
        (ProviderErrorClass.MODEL_NOT_FOUND, True),
        (ProviderErrorClass.TIMEOUT, False),
    ],
)
async def test_a_provider_failure_is_classified(
    error_class: ProviderErrorClass, infrastructure: bool
) -> None:
    with pytest.raises(DirectionError) as caught:
        await judge(ProviderError(error_class, "down"))
    assert caught.value.counts_as_attempt is not infrastructure


async def test_a_long_description_is_cut_to_the_limit() -> None:
    provider = FakeProvider([answer()])
    long_text = DESCRIPTION + " filler" * 5000
    result = await DirectionJudge(provider, max_chars=2000).judge(
        TARGET, title=TITLE, description=long_text
    )
    assert result.level == "strong"
    assert len(provider.requests[0].user) < 4000
