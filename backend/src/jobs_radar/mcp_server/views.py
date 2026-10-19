"""Compact answers for agents, shaped from the API's JSON (ADR-078).

The views are this package's own contract: they pick the fields an agent can use, so the tool
output does not change when an API model gains a field, and they keep replies small. Text that
third parties wrote (job descriptions, the quotes the model took from them, the AI summary) only
leaves through :func:`wrap_untrusted`. The profile and the intents are returned in full by the
owner's decision, minus any key that looks like a secret.
"""

import json
import re
from typing import Any, cast

from pydantic import BaseModel

from jobs_radar.mcp_server.untrusted import wrap_untrusted

EVIDENCE_MAX_CHARS = 600
SUMMARY_MAX_CHARS = 3000
MAX_OFFERS = 20
MAX_FACTS = 40
FACT_MAX_CHARS = 500

# A key that looks like a secret is never returned, whatever the API sends (defence in depth).
_SECRET_KEY = re.compile(r"credential|secret|api_?key|token|password", re.IGNORECASE)


def prune_secrets(value: Any) -> Any:
    """Return ``value`` without any mapping key that looks like a secret, at any depth."""
    if isinstance(value, dict):
        return {k: prune_secrets(v) for k, v in value.items() if not _SECRET_KEY.search(str(k))}
    if isinstance(value, list):
        return [prune_secrets(item) for item in value]
    return value


def prune_mapping(value: dict[str, Any]) -> dict[str, Any]:
    """Typed form of :func:`prune_secrets` for a mapping."""
    return cast(dict[str, Any], prune_secrets(value))


class StatusView(BaseModel):
    """Is the stack up, what the worker is doing, and what waits for review."""

    status: str
    components: dict[str, str]
    pipeline_state: str
    ai_model: str | None
    worker: dict[str, Any]
    analysis_queue: dict[str, Any]
    scoring_queue: dict[str, Any]
    failures: dict[str, Any]
    to_review: int
    to_review_high_fit: int
    fit_threshold: int
    best_fit: int | None
    followed_recommended: int


class EvaluationView(BaseModel):
    """The score of a job under one intent."""

    fit_score: int
    fit_band: str
    recommendation: str
    policy_version: str
    gates: list[dict[str, str]]


class InboxRow(BaseModel):
    """One job of the inbox, without its text."""

    job_inbox_item_id: int
    job_posting_id: int
    version: int
    title: str
    company: str
    company_id: int
    locations: list[str]
    state: str
    is_shortlisted: bool
    closed: bool
    evaluated: bool
    evaluation: EvaluationView | None
    engagement_types: list[str]
    pay: dict[str, Any] | None
    possible_duplicate: bool
    sources: list[str]
    first_seen_at: str
    last_seen_at: str
    applied_at: str | None
    note: str | None


class InboxPage(BaseModel):
    """A page of the inbox with the counts of every tab."""

    items: list[InboxRow]
    counts: dict[str, int]
    next_cursor: str | None
    search_intent_id: int | None
    set_aside_below_fit: int


class DimensionView(BaseModel):
    """How one scoring dimension came out."""

    dimension: str
    status: str
    quality: str | None
    weight: int
    contribution: float
    excluded: bool
    explanation: str
    untrusted_evidence: str


class JobView(BaseModel):
    """A job with its facts, score evidence and (wrapped) text."""

    summary: InboxRow
    apply_url: str | None
    source_url: str | None
    key_facts: list[str]
    technologies: list[dict[str, str]]
    untrusted_ai_summary: str | None
    dimensions: list[DimensionView]
    last_change: dict[str, Any] | None
    history: list[dict[str, Any]]
    untrusted_description: str


def status_view(pipeline: dict[str, Any], widget: dict[str, Any]) -> StatusView:
    """Merge the pipeline status and the dashboard summary."""
    return StatusView(
        status=widget["status"],
        components=widget.get("components", {}),
        pipeline_state=pipeline["state"],
        ai_model=pipeline.get("ai_model"),
        worker=pipeline["worker"],
        analysis_queue=pipeline["analysis"],
        scoring_queue=pipeline["scoring"],
        failures=pipeline["failures"],
        to_review=widget["to_review"],
        to_review_high_fit=widget["to_review_high_fit"],
        fit_threshold=widget["fit_threshold"],
        best_fit=widget.get("best_fit"),
        followed_recommended=widget["followed_recommended"],
    )


def _evaluation(raw: dict[str, Any] | None) -> EvaluationView | None:
    if raw is None:
        return None
    return EvaluationView(
        fit_score=raw["fit_score"],
        fit_band=raw["fit_band"],
        recommendation=raw["recommendation"],
        policy_version=raw["policy_version"],
        gates=[{"code": g["code"], "reason": g["reason"]} for g in raw.get("gates", [])],
    )


def inbox_row(raw: dict[str, Any]) -> InboxRow:
    """Shape one inbox item (list row or detail) without any long text."""
    return InboxRow(
        job_inbox_item_id=raw["job_inbox_item_id"],
        job_posting_id=raw["job_posting_id"],
        version=raw["version"],
        title=raw["title"],
        company=raw["company_name"],
        company_id=raw["company_id"],
        locations=raw["locations"],
        state=raw["state"],
        is_shortlisted=raw["is_shortlisted"],
        closed=raw["closed"],
        evaluated=raw["evaluated"],
        evaluation=_evaluation(raw.get("evaluation")),
        engagement_types=raw.get("engagement_types", []),
        pay=raw.get("pay"),
        possible_duplicate=raw["possible_duplicate"],
        sources=sorted({s["source_name"] for s in raw.get("sources", [])}),
        first_seen_at=raw["first_seen_at"],
        last_seen_at=raw["last_seen_at"],
        applied_at=raw.get("applied_at"),
        note=raw.get("note"),
    )


def inbox_page(raw: dict[str, Any]) -> InboxPage:
    """Shape a page of ``GET /inbox``."""
    return InboxPage(
        items=[inbox_row(item) for item in raw["items"]],
        counts=raw["counts"],
        next_cursor=raw.get("next_cursor"),
        search_intent_id=raw.get("search_intent_id"),
        set_aside_below_fit=raw["set_aside_below_fit"],
    )


def _dimension(raw: dict[str, Any]) -> DimensionView:
    # The evidence holds quotes the model took from the posting: third-party text.
    evidence = json.dumps(
        prune_secrets(raw.get("evidence", {})), ensure_ascii=False, sort_keys=True
    )
    return DimensionView(
        dimension=raw["dimension_key"],
        status=raw["status"],
        quality=raw.get("quality"),
        weight=raw["weight"],
        contribution=raw["contribution"],
        excluded=raw["excluded"],
        explanation=raw["explanation"],
        untrusted_evidence=wrap_untrusted(evidence, max_chars=EVIDENCE_MAX_CHARS),
    )


def job_view(raw: dict[str, Any], *, max_chars: int) -> JobView:
    """Shape ``GET /inbox/{id}``: facts and score evidence, the text only inside the wrapper."""
    brief = raw.get("brief", {})
    ai_summary = brief.get("summary")
    return JobView(
        summary=inbox_row(raw),
        apply_url=raw.get("apply_url"),
        source_url=raw.get("source_url"),
        key_facts=brief.get("facts", []),
        technologies=[
            {"name": t["name"], "importance": t["importance"]}
            for t in brief.get("technologies", [])
        ],
        untrusted_ai_summary=(
            wrap_untrusted(ai_summary, max_chars=SUMMARY_MAX_CHARS) if ai_summary else None
        ),
        dimensions=[_dimension(d) for d in raw.get("dimensions", [])],
        last_change=raw.get("last_change"),
        history=[
            {k: e[k] for k in ("action", "actor", "from_state", "to_state", "created_at")}
            for e in raw.get("events", [])
        ],
        untrusted_description=wrap_untrusted(raw["description_text"], max_chars=max_chars),
    )


def digest_view(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape the daily digest: new high-fit jobs, changed shortlisted jobs, source problems."""
    return {
        "since": raw["since"],
        "generated_at": raw["generated_at"],
        "alert_threshold": raw["alert_threshold"],
        "search_intent_id": raw.get("search_intent_id"),
        "counts": raw["counts"],
        "last_run": prune_secrets(raw.get("last_run")),
        "new_high_fit": [inbox_row(i).model_dump() for i in raw["new_high_fit"]],
        "changed_shortlisted": [
            {
                "changed_at": c["changed_at"],
                "changed_fields": c["changed_fields"],
                "item": inbox_row(c["item"]).model_dump(),
            }
            for c in raw["changed_shortlisted"]
        ],
        "source_health": prune_secrets(raw["source_health"]),
    }


def source_view(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape one source; whether a key is saved is shown, never the key itself."""
    return {
        "source_configuration_id": raw["source_configuration_id"],
        "source_type": raw["source_type"],
        "category": raw["category"],
        "display_name": raw["display_name"],
        "company_name": raw.get("company_name"),
        "enabled": raw["enabled"],
        "open_postings": raw["open_postings"],
        "rate_limit_per_minute": raw["rate_limit_per_minute"],
        "next_run_allowed_at": raw.get("next_run_allowed_at"),
        "needs_key": raw["credential_status"] != "not_needed",
        "key_saved": raw["credential_status"] == "saved",
        "filters": prune_secrets(raw.get("filters")),
        "last_result": prune_secrets(raw.get("last_result")),
    }


def run_view(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape one collection run with its per-source outcomes."""
    return prune_mapping(
        {
            "collection_run_id": raw["collection_run_id"],
            "status": raw["status"],
            "trigger": raw["trigger"],
            "source_configuration_id": raw.get("source_configuration_id"),
            "requested_at": raw["requested_at"],
            "started_at": raw.get("started_at"),
            "finished_at": raw.get("finished_at"),
            "error_class": raw.get("error_class"),
            "results": [
                {
                    k: r.get(k)
                    for k in (
                        "source_configuration_id",
                        "outcome",
                        "collected_count",
                        "new_count",
                        "updated_count",
                        "closed_count",
                        "dropped_count",
                        "error_class",
                        "error_message",
                        "duration_ms",
                    )
                }
                for r in raw.get("results", [])
            ],
        }
    )


def company_row(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape one company of the list."""
    return {
        k: raw.get(k)
        for k in (
            "company_id",
            "name",
            "homepage_url",
            "careers_url",
            "employer_type",
            "is_followed",
            "is_ignored",
            "has_source",
            "open_offers",
            "recommended_offers",
            "best_fit_score",
            "pending_candidates",
        )
    }


def _fact(raw: dict[str, Any]) -> dict[str, Any]:
    """One dossier fact; its value comes from public sites, so it goes in the wrapper."""
    value = raw.get("value")
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return {
        "label": raw.get("label"),
        "untrusted_value": wrap_untrusted(text, max_chars=FACT_MAX_CHARS),
        "source_name": raw.get("source_name"),
        "source_url": raw.get("source_url"),
        "licence": raw.get("licence"),
        "retrieved_at": raw.get("retrieved_at"),
    }


def company_dossier(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape a company dossier: facts with provenance, boards and the latest offers."""
    offers = raw.get("offers", [])
    return {
        **company_row(raw),
        "enriched_at": raw.get("enriched_at"),
        "stale": raw.get("stale", False),
        "warnings": raw.get("warnings", []),
        "facts": [_fact(f) for f in raw.get("facts", [])[:MAX_FACTS]],
        "boards": [
            {k: b.get(k) for k in ("display_name", "source_type", "enabled", "last_outcome")}
            for b in raw.get("boards", [])
        ],
        "offers": [
            {
                k: o.get(k)
                for k in (
                    "job_inbox_item_id",
                    "title",
                    "state",
                    "fit_score",
                    "fit_band",
                    "recommendation",
                    "is_shortlisted",
                    "closed",
                    "first_seen_at",
                )
            }
            for o in offers[:MAX_OFFERS]
        ],
        "offers_truncated": bool(raw.get("offers_truncated")) or len(offers) > MAX_OFFERS,
        "hiring_weeks": raw.get("hiring", []),
    }


def trends_view(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape the trend report (already compact; secrets pruned for safety)."""
    return prune_mapping(
        {
            k: raw.get(k)
            for k in (
                "kind",
                "search_intent_id",
                "relevance_min_score",
                "available_weeks",
                "first_week",
                "periods",
                "weeks",
                "rows",
                "intent_revision_changes",
                "source_set_changes",
            )
        }
    )
