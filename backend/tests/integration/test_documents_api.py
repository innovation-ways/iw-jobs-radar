"""CV upload: validation, in-memory handling and safe metadata only (T6.4, ADR-010)."""

import hashlib
import tempfile

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.document_files import docx_bytes, pdf_bytes, text_bytes

from jobs_radar.db.models import Document

pytestmark = pytest.mark.integration

URL = "/api/v1/documents"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture(autouse=True)
async def clean(session_factory: async_sessionmaker[AsyncSession]):  # type: ignore[no-untyped-def]
    yield
    async with session_factory() as session:
        await session.execute(delete(Document))
        await session.commit()


async def upload(client: httpx.AsyncClient, name: str, data: bytes, mime: str) -> httpx.Response:
    return await client.post(URL, files={"file": (name, data, mime)})


async def test_a_pdf_is_extracted_and_only_safe_metadata_is_returned(
    client: httpx.AsyncClient,
) -> None:
    data = pdf_bytes(pages=2)
    response = await upload(client, "cv.pdf", data, "application/pdf")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["sha256"] == hashlib.sha256(data).hexdigest()
    assert (body["mime_type"], body["byte_size"], body["extraction_status"]) == (
        "application/pdf",
        len(data),
        "extracted",
    )
    assert body["pages"] == 2 and body["characters"] > 100 and body["text_available"] is True
    assert "Alex Example" not in response.text  # no content comes back, only counts

    again = (await client.get(f"{URL}/{body['document_id']}")).json()
    assert again["document_id"] == body["document_id"] and again["text_available"] is True
    assert "Alex" not in str(again)


async def test_word_and_text_files_are_accepted(client: httpx.AsyncClient) -> None:
    assert (await upload(client, "cv.docx", docx_bytes(), DOCX)).status_code == 201
    assert (await upload(client, "cv.txt", text_bytes(), "text/plain")).status_code == 201


async def test_a_scanned_pdf_needs_ocr_and_has_no_text(client: httpx.AsyncClient) -> None:
    body = (await upload(client, "scan.pdf", pdf_bytes(lines=[]), "application/pdf")).json()
    assert body["extraction_status"] == "needs_ocr" and body["text_available"] is False


@pytest.mark.parametrize(
    ("name", "data", "mime", "reason"),
    [
        ("cv.exe", b"MZ....", "application/octet-stream", "unsupported_type"),
        ("cv.pdf", b"not a pdf", "application/pdf", "unsupported_type"),
        ("cv.pdf", b"%PDF-1.4 broken broken", "application/pdf", "corrupt"),
        ("cv.txt", b"", "text/plain", "empty"),
        ("cv.txt", b"a" * (5 * 1024 * 1024 + 1), "text/plain", "too_large"),
    ],
)
async def test_unusable_files_are_422_and_nothing_is_saved(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    name: str,
    data: bytes,
    mime: str,
    reason: str,
) -> None:
    response = await upload(client, name, data, mime)
    assert response.status_code == 422
    assert response.json()["error"]["details"]["error_class"] == reason
    async with session_factory() as session:
        assert (await session.execute(select(Document))).scalars().all() == []


async def test_a_missing_file_part_is_422(client: httpx.AsyncClient) -> None:
    assert (await client.post(URL, data={"x": "y"})).status_code == 422


async def test_unknown_documents_are_404(client: httpx.AsyncClient) -> None:
    assert (await client.get(f"{URL}/999999")).status_code == 404


async def test_nothing_is_written_to_disk_even_for_a_large_upload(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        msg = "an upload must never touch the disk"
        raise AssertionError(msg)

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", refuse)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", refuse)
    monkeypatch.setattr(tempfile, "mkstemp", refuse)
    big = ("Python engineer with PostgreSQL experience. " * 40000).encode()[: 3 * 1024 * 1024]
    assert (await upload(client, "big.txt", big, "text/plain")).status_code == 201
