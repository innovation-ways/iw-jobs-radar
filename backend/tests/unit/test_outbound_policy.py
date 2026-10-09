"""Static guards for the network and disk policy (ADR-035, ADR-010, T8.2)."""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "jobs_radar"


def test_only_the_guarded_client_imports_the_http_library() -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if re.search(
            r"^\s*(import|from)\s+(httpx|requests|urllib\.request|aiohttp)\b",
            path.read_text(),
            re.M,
        )
        and path.name != "http.py"
    ]
    assert offenders == [], f"outbound calls must go through core/http.py: {offenders}"


def test_upload_and_cv_code_never_writes_files() -> None:
    names = [
        "adapters/documents/extract.py",
        "services/documents.py",
        "services/proposals.py",
        "services/document_store.py",
        "api/routes/documents.py",
    ]
    for name in names:
        text = (SRC / name).read_text()
        assert not re.search(
            r"\b(open\(|write_bytes|write_text|NamedTemporaryFile|mkstemp|tempfile)\b", text
        ), name


def test_sockets_are_only_opened_by_the_guard_and_the_database_driver() -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if re.search(r"^\s*import socket\b", path.read_text(), re.M) and path.name != "url_guard.py"
    ]
    assert offenders == []
