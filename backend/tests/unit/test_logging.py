"""Unit tests for structured logging, secret redaction and request ids (ADR-036)."""

import json

import pytest
import structlog

from jobs_radar.core.logging import (
    bind_request_id,
    configure_logging,
    redact_secrets,
    reset_request_id,
)


def test_redacts_known_secret_keys_recursively() -> None:
    event = {
        "event": "x",
        "password": "p",
        "nested": {"api_key": "k", "Authorization": "Bearer abc", "safe": "ok"},
        "items": [{"token": "t"}],
    }
    result = redact_secrets(None, "info", event)
    assert result["password"] == "[REDACTED]"
    assert result["nested"]["api_key"] == "[REDACTED]"
    assert result["nested"]["Authorization"] == "[REDACTED]"
    assert result["nested"]["safe"] == "ok"
    assert result["items"][0]["token"] == "[REDACTED]"


def test_never_logs_cv_text_descriptions_or_prompts() -> None:
    event = {"event": "x", "cv_text": "secret cv", "description": "long text", "prompt": "p"}
    result = redact_secrets(None, "info", event)
    assert result["cv_text"] == "[REDACTED]"
    assert result["description"] == "[REDACTED]"
    assert result["prompt"] == "[REDACTED]"


def test_request_id_is_added_to_log_lines(capsys: object) -> None:
    configure_logging("INFO")
    token = bind_request_id("req-123")
    try:
        structlog.get_logger().info("hello", password="nope")
    finally:
        reset_request_id(token)
    out = capsys.readouterr().out.strip().splitlines()[-1]  # type: ignore[attr-defined]
    line = json.loads(out)
    assert line["request_id"] == "req-123"
    assert line["event"] == "hello"
    assert line["password"] == "[REDACTED]"
    assert "timestamp" in line


def test_redaction_covers_every_secret_and_content_key_used_by_later_tasks() -> None:
    keys = [
        "github_token",
        "credential_key",
        "credential_ciphertext",
        "api_key",
        "secret",
        "source_excerpt",
        "extracted_text",
        "raw_text",
    ]
    result = redact_secrets(None, "info", {"event": "x", **dict.fromkeys(keys, "v")})
    assert {key: result[key] for key in keys} == dict.fromkeys(keys, "[REDACTED]")


@pytest.mark.parametrize(
    "text",
    [
        "GET https://api.example.test/job/list.json?api_key=s3cretvalue&page=2",
        "https://api.example.test/x?page=1&key=s3cretvalue",
        "https://api.example.test/x?token=s3cretvalue",
    ],
)
def test_secrets_in_query_strings_are_masked_inside_log_values(text: str) -> None:
    from jobs_radar.core.logging import redact_secrets

    event = redact_secrets(None, "info", {"event": "fetch", "detail": text})
    assert "s3cretvalue" not in str(event)
    assert "page" in str(event) or "token" in str(event)
