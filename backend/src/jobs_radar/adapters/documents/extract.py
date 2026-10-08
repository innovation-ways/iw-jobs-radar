"""Extract text from an uploaded CV entirely in memory (T6.4, ADR-010).

The file type is decided by the content, not by the name or the declared MIME type. Nothing is
written to disk, and the bytes are not kept: the caller receives the text and drops the original.
Hostile input is bounded: size, page count and the uncompressed size of Word documents. Errors carry
a stable ``reason`` and never include any content of the file.
"""

import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePath

from docx import Document as DocxDocument
from pypdf import PdfReader
from pypdf.errors import PyPdfError

EXTRACTOR_VERSION = "extract-v1"
MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 50
# A .docx is a zip; refuse one that expands beyond this (zip-bomb guard).
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
# Fewer characters than this in a PDF means a scan: it needs OCR, which V1 does not offer.
MIN_PDF_CHARACTERS = 50

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEXT = "text/plain"
_BY_EXTENSION = {".pdf": PDF, ".docx": DOCX, ".txt": TEXT, ".md": TEXT}


class DocumentError(Exception):
    """The upload cannot be used; ``reason`` is unsupported_type, too_large, empty or corrupt."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class ExtractedText:
    """The text of a document (kept in memory only) and safe metadata about it."""

    text: str
    mime_type: str
    status: str  # extracted | needs_ocr
    pages: int | None
    characters: int


def _refuse(reason: str, message: str) -> DocumentError:
    return DocumentError(reason, message)


def extract_text(filename: str, declared_mime: str | None, data: bytes) -> ExtractedText:
    """Return the text of ``data`` or raise :class:`DocumentError`.

    Args:
        filename: the uploaded name; only its extension is used.
        declared_mime: the client's MIME type; informational, never trusted.
        data: the file content.
    """
    del declared_mime  # the content decides the type
    if not data:
        raise _refuse("empty", "The file is empty.")
    if len(data) > MAX_BYTES:
        raise _refuse("too_large", f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    expected = _BY_EXTENSION.get(PurePath(filename).suffix.lower())
    if expected is None:
        raise _refuse(
            "unsupported_type", "Only PDF, Word (.docx), .txt and .md files are accepted."
        )
    if expected == PDF:
        return _pdf(data)
    if expected == DOCX:
        return _docx(data)
    return _text(data)


def _pdf(data: bytes) -> ExtractedText:
    if not data.startswith(b"%PDF-"):
        raise _refuse("unsupported_type", "The file is not a PDF.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > MAX_PAGES:
            raise _refuse("too_large", f"The PDF has more than {MAX_PAGES} pages.")
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        pages = len(reader.pages)
    except DocumentError:
        raise
    # Intentionally broad: the PDF parser can raise many error types on hostile or damaged input,
    # and none of them may leak file content or crash the request.
    except (PyPdfError, ValueError, KeyError, TypeError, RecursionError, OSError) as exc:
        raise _refuse("corrupt", "The PDF could not be read.") from exc
    if len(text) < MIN_PDF_CHARACTERS:
        return ExtractedText("", PDF, "needs_ocr", pages, 0)
    return ExtractedText(text, PDF, "extracted", pages, len(text))


def _docx(data: bytes) -> ExtractedText:
    if not data.startswith(b"PK"):
        raise _refuse("unsupported_type", "The file is not a Word document.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise _refuse("too_large", "The document expands to an unreasonable size.")
        document = DocxDocument(io.BytesIO(data))
        parts = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            parts.extend(" | ".join(cell.text for cell in row.cells) for row in table.rows)
    except DocumentError:
        raise
    # Intentionally broad for the same reason as for PDF: damaged zips and XML raise many types.
    except (zipfile.BadZipFile, KeyError, ValueError, TypeError, OSError) as exc:
        raise _refuse("corrupt", "The Word document could not be read.") from exc
    text = "\n".join(part for part in parts if part.strip()).strip()
    return ExtractedText(text, DOCX, "extracted", None, len(text))


def _text(data: bytes) -> ExtractedText:
    if b"\x00" in data:
        raise _refuse("unsupported_type", "The file is not plain text.")
    try:
        text = data.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise _refuse("corrupt", "The text file is not valid UTF-8.") from exc
    return ExtractedText(text, TEXT, "extracted", None, len(text))
