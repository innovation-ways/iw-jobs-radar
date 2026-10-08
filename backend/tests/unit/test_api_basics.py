"""Unit tests for the HTTP layer: health, error envelope and request ids (document 07, ADR-036/037)."""

from collections.abc import Iterator

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from jobs_radar.api.app import create_app
from jobs_radar.api.deps import get_readiness_service
from jobs_radar.core.errors import (
    ConflictError,
    DependencyUnavailableError,
    InputValidationError,
    NotFoundError,
)
from jobs_radar.core.settings import Settings
from jobs_radar.services.readiness import ComponentStatus, ReadinessReport


class FakeReadiness:
    """Readiness service stub returning a fixed report."""

    def __init__(self, database: str, worker: str) -> None:
        self.report = ReadinessReport(
            database=ComponentStatus(database), worker=ComponentStatus(worker)
        )

    async def check(self) -> ReadinessReport:
        return self.report


class Payload(BaseModel):
    """Request body used to trigger a validation error."""

    count: int


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(_env_file=None, db_password="pw")  # type: ignore[call-arg]
    app = create_app(settings)
    router = APIRouter()

    @router.get("/boom/{kind}")
    async def boom(kind: str) -> None:
        errors = {
            "conflict": ConflictError("stale version", details={"expected": 1}),
            "missing": NotFoundError("no such thing"),
            "invalid": InputValidationError("bad input"),
            "down": DependencyUnavailableError("provider unreachable"),
        }
        if kind == "crash":
            raise RuntimeError("secret internal detail")
        raise errors[kind]

    @router.post("/echo")
    async def echo(payload: Payload) -> Payload:
        return payload

    app.include_router(router, prefix="/api/v1")
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_healthz_needs_no_database(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("kind", "status", "code"),
    [
        ("conflict", 409, "conflict"),
        ("missing", 404, "not_found"),
        ("invalid", 422, "validation_error"),
        ("down", 503, "dependency_unavailable"),
    ],
)
def test_domain_errors_use_the_error_envelope(
    client: TestClient, kind: str, status: int, code: str
) -> None:
    response = client.get(f"/api/v1/boom/{kind}")
    assert response.status_code == status
    error = response.json()["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    assert error["code"] == code
    assert error["request_id"] == response.headers["x-request-id"]


def test_conflict_carries_details(client: TestClient) -> None:
    error = client.get("/api/v1/boom/conflict").json()["error"]
    assert error["details"] == {"expected": 1}


def test_unknown_route_is_a_404_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_schema_validation_is_a_422_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/echo", json={"count": "not-a-number"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]["errors"], "field errors are listed"


def test_unhandled_errors_are_a_500_envelope_without_internal_detail(client: TestClient) -> None:
    response = client.get("/api/v1/boom/crash")
    assert response.status_code == 500
    assert "secret internal detail" not in response.text
    assert response.json()["error"]["code"] == "internal_error"


def test_incoming_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"


def test_request_id_is_generated_when_missing(client: TestClient) -> None:
    assert client.get("/healthz").headers["x-request-id"]


@pytest.mark.parametrize(
    ("database", "worker", "status"),
    [("up", "up", 200), ("down", "up", 503), ("up", "stale", 503), ("up", "missing", 503)],
)
def test_readyz_reflects_component_state(
    client: TestClient, database: str, worker: str, status: int
) -> None:
    client.app.dependency_overrides[get_readiness_service] = lambda: FakeReadiness(  # type: ignore[attr-defined]
        database, worker
    )
    response = client.get("/readyz")
    assert response.status_code == status
    body = response.json()
    assert body["components"] == {"database": database, "worker": worker}
    assert body["status"] == ("ready" if status == 200 else "unavailable")
