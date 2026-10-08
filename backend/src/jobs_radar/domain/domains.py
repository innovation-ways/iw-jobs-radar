"""Domain-name helpers for matching a company to a public dataset entry (ADR-025).

A match is accepted automatically only when the registered domain of the entity's official website
equals a registered domain already known for the company. Pure functions.
"""

import ipaddress
import re
from urllib.parse import urlsplit

# Second-level labels under which a registered domain has three labels (co.uk, com.au, ...).
_SECOND_LEVEL = frozenset({"co", "com", "org", "net", "gov", "edu", "ac"})
_JOB_BOARD_SUFFIXES = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "workable.com",
    "smartrecruiters.com",
)
_LABEL = re.compile(r"^[a-z0-9-]{1,63}$")


def _host(url: str) -> str | None:
    text = url.strip()
    if not text:
        return None
    if "://" not in text:
        text = f"https://{text}"
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"}:
        return None
    host = (parts.hostname or "").lower().rstrip(".")
    return host or None


def registered_domain(url: str) -> str | None:
    """Return the registered domain of ``url`` (``www.a.co.uk`` -> ``a.co.uk``), or ``None``."""
    host = _host(url)
    if host is None:
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return None
    labels = host.split(".")
    if len(labels) < 2 or not all(_LABEL.match(label) for label in labels):
        return None
    keep = 3 if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2 else 2
    return ".".join(labels[-keep:])


def is_job_board_host(url: str) -> bool:
    """Whether ``url`` is on a third-party job board (its domain says nothing about the company)."""
    domain = registered_domain(url)
    return domain is not None and domain in _JOB_BOARD_SUFFIXES
