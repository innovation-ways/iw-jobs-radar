"""Structured JSON logging with secret redaction and request ids (ADR-036)."""

import logging
import sys
from collections.abc import Mapping, MutableMapping
from contextvars import ContextVar, Token
from typing import Any

import structlog

REDACTED = "[REDACTED]"

# Keys whose values must never be logged: credentials, and private content (CV text, job
# descriptions, prompts) that the privacy rules forbid in logs (TR-5.4).
_SENSITIVE_PARTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "cookie",
    "cv_text",
    "description",
    "prompt",
)

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_PARTS)


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: REDACTED if _is_sensitive(str(k)) else _redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(item) for item in value]
    return value


def redact_secrets(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Mask sensitive keys at any nesting depth (structlog processor)."""
    redacted = _redact(dict(event_dict))
    event_dict.clear()
    event_dict.update(redacted)
    return event_dict


def bind_request_id(request_id: str) -> Token[str | None]:
    """Bind a request id to the current context and return the token to reset it."""
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Undo :func:`bind_request_id`."""
    _request_id.reset(token)


def current_request_id() -> str | None:
    """Return the request id bound to the current context, if any."""
    return _request_id.get()


def _add_request_id(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    request_id = _request_id.get()
    if request_id is not None:
        event_dict["request_id"] = request_id
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog to emit one JSON object per line on stdout."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level, force=True)
    structlog.configure(
        processors=[
            _add_request_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_secrets,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )
