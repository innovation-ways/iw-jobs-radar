"""Remove contact details from text before it can leave the machine (T6.3, document 08).

Replaces e-mail addresses, phone numbers and links (including profile URLs such as LinkedIn and
GitHub) with placeholders. Names and places stay: they are needed to read a CV and are covered by
the per-document consent, not by redaction. Pure functions; the policy name is stored with each
proposal.
"""

import re
from dataclasses import dataclass, field

REDACTION_POLICY = "contact-v1"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)
_LINK = re.compile(
    r"(?:https?://|www\.)[^\s<>\"')]+"
    r"|(?:[a-z0-9-]+\.)?(?:linkedin|github|gitlab|bitbucket|xing|twitter|x)\.(?:com|net|org)/[^\s<>\"')]+",
    re.IGNORECASE,
)
# A phone number: an optional international prefix, then digit groups separated by space, dot,
# dash or parentheses, with at least 9 digits in total. Dates (2019-03, 12/2020) have fewer digits
# and use other separators, so they are left alone.
_PHONE = re.compile(r"(?<![\w/])(?:\+|00)?(?:\(?\d{1,4}\)?[\s.-]?){2,6}\d{2,4}(?![\w/])")


@dataclass(frozen=True)
class Redacted:
    """The redacted text and how many items of each kind were removed."""

    text: str
    counts: dict[str, int] = field(default_factory=dict)


def _digits(value: str) -> int:
    return sum(ch.isdigit() for ch in value)


def redact_contact_details(text: str) -> Redacted:
    """Replace e-mails, links and phone numbers in ``text`` with placeholders."""
    counts = {"email": 0, "link": 0, "phone": 0}

    def swap(kind: str, placeholder: str):  # type: ignore[no-untyped-def]
        def replace(match: re.Match[str]) -> str:
            counts[kind] += 1
            return placeholder

        return replace

    text = _EMAIL.sub(swap("email", "[EMAIL]"), text)
    text = _LINK.sub(swap("link", "[LINK]"), text)

    def phone(match: re.Match[str]) -> str:
        if _digits(match.group()) < 9:
            return match.group()  # a year range, a date or a short number: not a phone
        counts["phone"] += 1
        return "[PHONE]"

    text = _PHONE.sub(phone, text)
    return Redacted(text=text, counts=counts)
