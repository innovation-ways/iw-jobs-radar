"""ASGI middleware: request ids and the last-resort error envelope (ADR-036, document 07)."""

import json
import re
import uuid
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from jobs_radar.core.logging import bind_request_id, reset_request_id

_REQUEST_ID_HEADER = b"x-request-id"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

logger = structlog.get_logger()


class RequestIdMiddleware:
    """Binds a request id to the log context and returns it as ``X-Request-ID``.

    It also converts any unhandled exception into the standard ``internal_error`` envelope, so
    that the response carries the request id and never leaks internal details.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI connection."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(_REQUEST_ID_HEADER, b"").decode("latin-1")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = bind_request_id(request_id)
        started = False

        async def send_with_id(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = [
                    h for h in message.get("headers", []) if h[0].lower() != _REQUEST_ID_HEADER
                ]
                headers.append((_REQUEST_ID_HEADER, request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        # Intentionally broad: this is the last line of defence and must always answer with the
        # standard envelope instead of letting the server emit a bare 500.
        except Exception:
            logger.exception("unhandled_error", path=scope.get("path"))
            if not started:
                body: dict[str, Any] = {
                    "error": {
                        "code": "internal_error",
                        "message": "Internal server error.",
                        "details": {},
                        "request_id": request_id,
                    }
                }
                payload = json.dumps(body).encode()
                await send_with_id(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(payload)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": payload})
        finally:
            reset_request_id(token)
