"""Application errors mapped to the HTTP error envelope of document 07.

Services raise these domain errors; the API layer turns them into ``{"error": {...}}`` bodies.
"""

from typing import Any


class AppError(Exception):
    """Base class for errors that are reported to API clients."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    """The requested resource does not exist (404)."""

    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    """A version or state conflict, for example a stale expected revision (409)."""

    status_code = 409
    code = "conflict"


class InputValidationError(AppError):
    """Input is well-formed but violates a domain rule (422)."""

    status_code = 422
    code = "validation_error"


class DependencyUnavailableError(AppError):
    """A configured external dependency, such as a provider or source, is unavailable (503)."""

    status_code = 503
    code = "dependency_unavailable"
