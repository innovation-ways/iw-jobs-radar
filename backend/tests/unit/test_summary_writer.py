"""The summary writer: prompt, answer checks and failures (ADR-059, prompt summary-v1)."""

import pytest
from tests.fake_provider import FakeProvider

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.domain.enums import SUMMARY_PROMPT_VERSION, ProviderErrorClass
from jobs_radar.services.summary_writer import SummaryError, SummaryWriter

COMPANY = "Acme Telecom"
TITLE = "Senior Java Engineer"
DESCRIPTION = "You will build the rating engine in Java.\nFully remote within the EU."
GOOD = (
    "Acme Telecom is hiring a senior Java engineer with five or more years of experience, "
    "fully remote within the EU. The work centres on the Java rating engine of its billing "
    "platform.\n\nYou would design and run the engine that prices usage events for operators. "
    "The posting does not state the pay."
)


async def write(*script: object, description: str = DESCRIPTION):  # type: ignore[no-untyped-def]
    provider = FakeProvider(list(script))
    writer = SummaryWriter(provider, max_chars=12000)
    return await writer.write(company=COMPANY, title=TITLE, description=description), provider


async def test_a_good_answer_is_kept() -> None:
    result, _ = await write({"summary": GOOD})
    assert result.text == GOOD
    assert result.latency_ms == 7


async def test_the_prompt_holds_the_job_only_and_asks_for_english() -> None:
    _, provider = await write({"summary": GOOD})
    request = provider.requests[0]
    assert COMPANY in request.user and TITLE in request.user and DESCRIPTION in request.user
    assert "English" in request.system
    assert set(request.json_schema["properties"]) == {"summary"}
    assert request.json_schema["properties"]["summary"]["maxLength"] == 1500
    assert SUMMARY_PROMPT_VERSION == "summary-v1"


async def test_a_long_description_is_cut_to_the_configured_size() -> None:
    provider = FakeProvider([{"summary": GOOD}])
    writer = SummaryWriter(provider, max_chars=100)
    await writer.write(company=COMPANY, title=TITLE, description="word " * 500)
    assert len(provider.requests[0].user) < 400


async def test_whitespace_is_tidied_and_paragraphs_are_kept() -> None:
    first = "First part of the summary is here, long enough to be a real summary of the job."
    result, _ = await write({"summary": f"  {first}  \n\n\n\n Second part \n continues. "})
    assert result.text == f"{first}\n\nSecond part continues."


@pytest.mark.parametrize("bad", ["", "   ", "Too short.", "x" * 1501])
async def test_an_unusable_answer_is_repaired_once_then_refused(bad: str) -> None:
    provider = FakeProvider([{"summary": bad}, {"summary": bad}])
    writer = SummaryWriter(provider, max_chars=12000)
    with pytest.raises(SummaryError) as caught:
        await writer.write(company=COMPANY, title=TITLE, description=DESCRIPTION)
    assert caught.value.error_class == "invalid_output" and caught.value.counts_as_attempt
    assert len(provider.requests) == 2
    assert "invalid" in provider.requests[1].user  # the repair note names the problem


async def test_a_repair_that_works_is_used() -> None:
    result, provider = await write("not json at all", {"summary": GOOD})
    assert result.text == GOOD and len(provider.requests) == 2


async def test_a_missing_field_is_repaired() -> None:
    result, _ = await write({"text": GOOD}, {"summary": GOOD})
    assert result.text == GOOD


@pytest.mark.parametrize(
    "error_class", [ProviderErrorClass.UNAVAILABLE, ProviderErrorClass.MODEL_NOT_FOUND]
)
async def test_a_model_that_is_down_does_not_use_an_attempt(
    error_class: ProviderErrorClass,
) -> None:
    provider = FakeProvider([ProviderError(error_class, "down")])
    with pytest.raises(SummaryError) as caught:
        await SummaryWriter(provider, max_chars=12000).write(
            company=COMPANY, title=TITLE, description=DESCRIPTION
        )
    assert not caught.value.counts_as_attempt


async def test_a_timeout_counts_but_is_not_an_invalid_answer() -> None:
    provider = FakeProvider([ProviderError(ProviderErrorClass.TIMEOUT, "slow")])
    with pytest.raises(SummaryError) as caught:
        await SummaryWriter(provider, max_chars=12000).write(
            company=COMPANY, title=TITLE, description=DESCRIPTION
        )
    assert caught.value.error_class == ProviderErrorClass.TIMEOUT.value
    assert caught.value.counts_as_attempt
