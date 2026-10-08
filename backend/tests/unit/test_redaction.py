"""Contact-detail redaction before any remote call (T6.3, document 08)."""

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jobs_radar.domain.redaction import REDACTION_POLICY, redact_contact_details

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def test_emails_are_replaced_by_a_placeholder() -> None:
    result = redact_contact_details("Mail me: jane.doe+cv@example.test or JANE@Example.Org.")
    assert "example" not in result.text.lower()
    assert result.text.count("[EMAIL]") == 2 and result.counts["email"] == 2


@pytest.mark.parametrize(
    "phone",
    [
        "+351 912 345 678",
        "+44 (0)20 7946 0958",
        "(555) 123-4567",
        "555-123-4567",
        "00351912345678",
        "+1.555.123.4567",
        "912 345 678",
    ],
)
def test_phone_numbers_in_common_formats_are_replaced(phone: str) -> None:
    result = redact_contact_details(f"Phone: {phone} (mobile)")
    assert phone not in result.text and "[PHONE]" in result.text


@pytest.mark.parametrize(
    "link",
    [
        "https://www.linkedin.com/in/jane-doe",
        "http://example.test/portfolio?id=1",
        "www.jane-doe.test",
        "linkedin.com/in/jane-doe",
        "github.com/janedoe",
    ],
)
def test_links_and_profile_urls_are_replaced(link: str) -> None:
    result = redact_contact_details(f"See {link} for more.")
    assert link not in result.text and "[LINK]" in result.text


def test_ordinary_content_is_left_alone() -> None:
    text = (
        "Senior engineer 2019-2023 at Northwind. Built 3 services handling 1,200 requests/s. "
        "Skills: Python 3.13, PostgreSQL 18, TypeScript. Based in Lisbon, Portugal."
    )
    result = redact_contact_details(text)
    assert result.text == text and sum(result.counts.values()) == 0


def test_dates_and_years_are_not_mistaken_for_phone_numbers() -> None:
    text = "From 2019-03 to 2023-11, 2015 - 2018 and 12/2020 - 05/2022."
    assert redact_contact_details(text).text == text


def test_the_policy_is_named_for_the_audit_record() -> None:
    assert REDACTION_POLICY == "contact-v1"


@given(
    st.from_regex(r"[a-z][a-z0-9._]{2,10}@[a-z]{3,8}\.(com|org|test)", fullmatch=True),
    st.text(alphabet=st.characters(whitelist_categories=("L", "Zs")), max_size=40),
)
def test_no_generated_email_survives(email: str, noise: str) -> None:
    result = redact_contact_details(f"{noise} {email} {noise}")
    assert EMAIL.search(result.text) is None


def test_pathological_input_does_not_hang() -> None:
    import time

    hostile = ("1 " * 3000) + ("9" * 5000) + ("(" * 2000) + "-" * 4000
    started = time.monotonic()
    redact_contact_details(hostile)
    assert time.monotonic() - started < 2
