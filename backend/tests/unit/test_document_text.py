"""In-memory text extraction from uploaded CVs (T6.4, ADR-010)."""

import pytest
from tests.document_files import CV_LINES, docx_bytes, pdf_bytes, text_bytes, zip_bomb_docx

from jobs_radar.adapters.documents.extract import (
    MAX_BYTES,
    DocumentError,
    extract_text,
)


def test_a_text_pdf_yields_its_text_and_page_count() -> None:
    result = extract_text("cv.pdf", "application/pdf", pdf_bytes(pages=2))
    assert result.status == "extracted" and result.pages == 2
    assert "Senior Software Engineer" in result.text and "PostgreSQL" in result.text
    assert result.mime_type == "application/pdf"


def test_a_pdf_without_text_is_marked_as_needing_ocr() -> None:
    result = extract_text("scan.pdf", "application/pdf", pdf_bytes(lines=[]))
    assert result.status == "needs_ocr" and result.text == ""


def test_a_word_document_yields_paragraphs_and_tables() -> None:
    data = docx_bytes(table=[["Company", "Years"], ["Northwind", "4"]])
    result = extract_text(
        "cv.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        data,
    )
    assert result.status == "extracted"
    assert "Senior Software Engineer" in result.text and "Northwind" in result.text


@pytest.mark.parametrize("name", ["cv.txt", "cv.md"])
def test_plain_text_is_decoded_including_a_byte_order_mark(name: str) -> None:
    data = b"\xef\xbb\xbf" + text_bytes()
    result = extract_text(name, "text/plain", data)
    assert result.status == "extracted" and result.text.startswith(CV_LINES[0])


def test_the_type_is_decided_by_content_not_by_the_declared_name() -> None:
    with pytest.raises(DocumentError) as caught:
        extract_text("cv.pdf", "application/pdf", b"MZ\x90\x00 not a pdf at all")
    assert caught.value.reason == "unsupported_type"
    with pytest.raises(DocumentError) as caught:
        extract_text("cv.docx", "application/zip", text_bytes())
    assert caught.value.reason == "unsupported_type"


@pytest.mark.parametrize("name", ["cv.exe", "cv", "cv.html", "cv.pdf.exe"])
def test_other_extensions_are_refused(name: str) -> None:
    with pytest.raises(DocumentError) as caught:
        extract_text(name, "application/octet-stream", text_bytes())
    assert caught.value.reason == "unsupported_type"


def test_oversized_and_empty_files_are_refused() -> None:
    with pytest.raises(DocumentError) as caught:
        extract_text("cv.txt", "text/plain", b"a" * (MAX_BYTES + 1))
    assert caught.value.reason == "too_large"
    with pytest.raises(DocumentError) as caught:
        extract_text("cv.txt", "text/plain", b"")
    assert caught.value.reason == "empty"


def test_corrupt_files_are_refused_without_leaking_content() -> None:
    with pytest.raises(DocumentError) as caught:
        extract_text("cv.pdf", "application/pdf", b"%PDF-1.4\n garbage garbage")
    assert caught.value.reason == "corrupt"
    assert "garbage" not in str(caught.value)
    with pytest.raises(DocumentError) as caught:
        extract_text(
            "cv.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            b"PK\x03\x04 broken",
        )
    assert caught.value.reason == "corrupt"


def test_binary_data_posing_as_text_is_refused() -> None:
    with pytest.raises(DocumentError) as caught:
        extract_text("cv.txt", "text/plain", b"abc\x00\x01\x02\xff\xfe binary")
    assert caught.value.reason in {"corrupt", "unsupported_type"}


def test_a_zip_bomb_is_refused() -> None:
    with pytest.raises(DocumentError) as caught:
        extract_text(
            "cv.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            zip_bomb_docx(),
        )
    assert caught.value.reason == "too_large"


def test_too_many_pages_are_refused() -> None:
    with pytest.raises(DocumentError) as caught:
        extract_text("cv.pdf", "application/pdf", pdf_bytes(lines=["x"], pages=60))
    assert caught.value.reason == "too_large"
