"""Pydantic models for the API error envelope (document 07)."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class ErrorBody(BaseModel):
    """The ``error`` object: a stable code, a human message, details and the request id."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any]
    request_id: str | None


class ErrorEnvelope(BaseModel):
    """Top-level error response."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorBody
