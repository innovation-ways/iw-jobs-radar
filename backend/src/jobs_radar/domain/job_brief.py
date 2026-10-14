"""The technologies and key facts shown above a job's description (ADR-059).

Both are read from the stored extraction output, so they cost no model call and carry the same
verified evidence as the score. Unknown attributes are left out: the briefing never fills a gap.
"""

from typing import Any

_WORK_MODES = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "On site"}


def _known(output: dict[str, Any], field: str) -> Any | None:
    """Return the value of an evidenced attribute, or ``None`` unless it is known."""
    attribute = output.get(field)
    if isinstance(attribute, dict) and attribute.get("status") == "known":
        return attribute.get("value")
    return None


def _label(key: str) -> str:
    """Turn a taxonomy key such as ``contractor_b2b`` into ``Contractor b2b``."""
    return key.replace("_", " ").capitalize()


def technologies(output: dict[str, Any]) -> list[dict[str, str]]:
    """Return the skills of the posting, required ones first, without repeats.

    Each item is ``{"name", "importance"}`` with importance ``must`` or ``nice``; the first
    spelling of a name wins and the extraction's order is kept inside each group.
    """
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    skills = output.get("skills") or []
    for importance in ("must", "nice"):
        for skill in skills:
            name = str(skill.get("name", "")).strip()
            if skill.get("importance") != importance or not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            items.append({"name": name, "importance": importance})
    return items


def _pay(value: dict[str, Any]) -> str | None:
    """Format a stated compensation as ``EUR 60,000-80,000 / year``."""
    if value.get("disclosed") is False:
        return None
    low, high = value.get("min"), value.get("max")
    if low is None or high is None:
        return None
    amount = f"{low:,.0f}" if low == high else f"{low:,.0f}-{high:,.0f}"
    return f"{value.get('currency', '')} {amount} / {value.get('period', '')}".strip()


def key_facts(output: dict[str, Any]) -> list[str]:
    """Return short labels for what the posting states, in a fixed order.

    Seniority, years of experience asked, work arrangement, employment type and pay.
    """
    facts: list[str] = []
    levels = _known(output, "seniority_levels")
    facts += [_label(level) for level in levels or []]
    years = _known(output, "years_required_min")
    if years:
        facts.append(f"{years}+ years")
    mode = _known(output, "work_mode")
    if mode in _WORK_MODES:
        facts.append(_WORK_MODES[mode])
    types = _known(output, "employment_types")
    facts += [_label(kind) for kind in types or []]
    pay = _known(output, "compensation")
    if isinstance(pay, dict) and (text := _pay(pay)):
        facts.append(text)
    return facts


def engagement_kinds(output: dict[str, Any]) -> list[str]:
    """Return the taxonomy keys of the engagement types the posting states (empty if unknown)."""
    return [str(kind) for kind in _known(output, "employment_types") or []]


def pay(output: dict[str, Any]) -> dict[str, Any] | None:
    """Return the stated pay as written (form, currency, range, period, text) or ``None``.

    Nothing is converted: an amount in another currency is returned in that currency (ADR-073).
    """
    value = _known(output, "compensation")
    if not isinstance(value, dict) or not (text := _pay(value)):
        return None
    return {
        "form": value.get("form"),
        "currency": value.get("currency"),
        "min": float(value["min"]),
        "max": float(value["max"]),
        "period": value.get("period"),
        "text": text,
    }
