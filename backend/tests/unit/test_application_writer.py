"""The pre-application writer: profile digest, prompt, evidence check and failures (ADR-064)."""

import pytest
from tests.fake_provider import FakeProvider

from jobs_radar.adapters.providers.base import ProviderError
from jobs_radar.domain.enums import APPLICATION_PROMPT_VERSION, ProviderErrorClass
from jobs_radar.schemas.profile import ProfileFacts
from jobs_radar.services.application_profile import describe_profile
from jobs_radar.services.application_writer import ApplicationError, ApplicationWriter

PROVENANCE = {"origin": "manual"}
FACTS = ProfileFacts.model_validate(
    {
        "headline": "Backend engineer for telecom platforms",
        "base_location": {"place": "Lisbon", "country": "PT", "timezone": "Europe/Lisbon"},
        "years_experience": 12,
        "languages": [{"language": "pt", "level": "native"}, {"language": "en", "level": "C1"}],
        "skills": [
            {"skill_id": 1, "level": "expert", "years": 10, "provenance": PROVENANCE},
            {"skill_id": 2, "level": "advanced", "years": 4, "provenance": PROVENANCE},
        ],
        "experience": [
            {
                "title": "Senior Engineer",
                "organisation": "Nova Telecom",
                "start": "2018-03",
                "summary": "Built the rating engine for prepaid billing.",
                "provenance": PROVENANCE,
            }
        ],
        "education": [{"level": "MSc", "field": "Informatics", "provenance": PROVENANCE}],
        "certifications": [{"name": "AWS Solutions Architect", "provenance": PROVENANCE}],
    }
)
SKILLS = {1: "Java", 2: "PostgreSQL"}
COMPANY, TITLE = "Acme Telecom", "Senior Java Engineer"
DESCRIPTION = "You will build the rating engine in Java.\nFully remote within the EU."


def strength(point: str, evidence: str) -> dict[str, str]:
    return {"point": point, "evidence": evidence}


GOOD_LETTER = " ".join(["I am writing to apply for the role."] * 30)
GOOD = {
    "strengths": [
        strength("Deep Java experience", "10 years of Java"),
        strength("Billing domain", "Built the rating engine at Nova Telecom"),
        strength("Database depth", "PostgreSQL, advanced"),
    ],
    "positioning": "Introduce yourself as a billing-platform engineer with a decade of Java.",
    "gaps": ["Kubernetes is not shown in the profile; mention any related exposure."],
    "cover_letter": GOOD_LETTER,
    "letter_language": "en",
}


async def write(*script: object):  # type: ignore[no-untyped-def]
    provider = FakeProvider(list(script))
    writer = ApplicationWriter(provider, max_chars=12000)
    digest = describe_profile(FACTS, SKILLS)
    result = await writer.write(
        company=COMPANY, title=TITLE, description=DESCRIPTION, digest=digest
    )
    return result, provider


def test_the_digest_lists_the_facts_and_the_words_evidence_may_use() -> None:
    digest = describe_profile(FACTS, SKILLS)
    for expected in ("Java", "expert", "Nova Telecom", "rating engine", "MSc", "AWS Solutions"):
        assert expected in digest.text
    assert {"java", "postgresql", "nova telecom", "senior engineer", "informatics"} <= (
        digest.vocabulary
    )


async def test_a_good_answer_is_kept_with_all_its_parts() -> None:
    result, _ = await write(GOOD)
    assert result.draft.strengths[0].point == "Deep Java experience"
    assert result.draft.letter_language == "en"
    assert result.draft.gaps and result.latency_ms == 7
    assert result.dropped_strengths == 0


async def test_the_prompt_holds_the_job_and_the_profile_but_no_contact_details() -> None:
    _, provider = await write(GOOD)
    request = provider.requests[0]
    assert COMPANY in request.user and TITLE in request.user and DESCRIPTION in request.user
    assert "Nova Telecom" in request.user and "Java" in request.user
    assert "Portuguese" in request.system and "English" in request.system
    assert set(request.json_schema["properties"]) == {
        "strengths",
        "positioning",
        "gaps",
        "cover_letter",
        "letter_language",
    }
    assert APPLICATION_PROMPT_VERSION == "application-v1"


async def test_a_strength_without_support_in_the_profile_is_dropped() -> None:
    invented = strength("Led a team of forty", "Managed forty engineers at Globex")
    answer = {**GOOD, "strengths": [*GOOD["strengths"], invented]}  # type: ignore[misc]
    result, _ = await write(answer)
    assert len(result.draft.strengths) == 3
    assert result.dropped_strengths == 1


async def test_too_few_supported_strengths_is_an_unusable_answer() -> None:
    weak = {**GOOD, "strengths": [GOOD["strengths"][0], strength("Rust", "Loves Rust")]}  # type: ignore[index]
    with pytest.raises(ApplicationError) as caught:
        await write(weak, weak)
    assert caught.value.error_class == "invalid_output"


@pytest.mark.parametrize(
    "bad",
    [
        {**GOOD, "cover_letter": "Too short."},
        {**GOOD, "letter_language": "fr"},
        {**GOOD, "positioning": ""},
        {"strengths": []},
    ],
)
async def test_an_unusable_answer_is_repaired_once_then_refused(bad: dict[str, object]) -> None:
    provider = FakeProvider([bad, bad])
    writer = ApplicationWriter(provider, max_chars=12000)
    with pytest.raises(ApplicationError) as caught:
        await writer.write(
            company=COMPANY,
            title=TITLE,
            description=DESCRIPTION,
            digest=describe_profile(FACTS, SKILLS),
        )
    assert caught.value.error_class == "invalid_output"
    assert len(provider.requests) == 2
    assert "invalid" in provider.requests[1].user


async def test_a_repair_that_works_is_accepted() -> None:
    result, provider = await write({"strengths": []}, GOOD)
    assert len(provider.requests) == 2 and len(result.draft.strengths) == 3


async def test_an_unreachable_model_is_reported_as_infrastructure() -> None:
    down = ProviderError(ProviderErrorClass.UNAVAILABLE, "down")
    with pytest.raises(ApplicationError) as caught:
        await write(down)
    assert caught.value.error_class == ProviderErrorClass.UNAVAILABLE.value
