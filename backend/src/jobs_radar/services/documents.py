"""Uploading a CV: validate, extract text in memory, keep only metadata (T6.4, ADR-010).

The bytes are hashed, read once and dropped. The extracted text goes to the short-lived in-memory
store so a proposal can be generated next; it is never written to the database or to disk.
"""

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobs_radar.adapters.documents.extract import (
    EXTRACTOR_VERSION,
    DocumentError,
    ExtractedText,
    extract_text,
)
from jobs_radar.core.errors import InputValidationError, NotFoundError
from jobs_radar.db.models import Document
from jobs_radar.services.document_store import DocumentTextStore


@dataclass(frozen=True)
class DocumentInfo:
    """A document with the safe facts the interface shows."""

    document: Document
    pages: int | None
    characters: int | None
    text_available: bool


class DocumentService:
    """Use cases for uploaded documents. The caller owns the transaction."""

    def __init__(self, session: AsyncSession, store: DocumentTextStore) -> None:
        self._session = session
        self._store = store

    async def upload(
        self, owner_id: int, filename: str, declared_mime: str | None, data: bytes
    ) -> DocumentInfo:
        """Extract the text of ``data`` in memory and record its metadata.

        Raises:
            InputValidationError: unsupported, empty, oversized or corrupt file (``error_class``
                in the details); nothing is saved.
        """
        try:
            extracted = extract_text(filename, declared_mime, data)
        except DocumentError as error:
            raise InputValidationError(
                error.message, details={"error_class": error.reason}
            ) from error
        document = Document(
            owner_id=owner_id,
            sha256=hashlib.sha256(data).hexdigest(),
            mime_type=extracted.mime_type,
            byte_size=len(data),
            extraction_status=extracted.status,
            extraction_version=EXTRACTOR_VERSION,
        )
        self._session.add(document)
        await self._session.flush()
        await self._session.refresh(document)
        if extracted.status == "extracted":
            self._store.put(document.document_id, extracted.text)
        return self._info(document, extracted)

    def _info(self, document: Document, extracted: ExtractedText | None = None) -> DocumentInfo:
        return DocumentInfo(
            document=document,
            pages=extracted.pages if extracted else None,
            characters=extracted.characters if extracted else None,
            text_available=self._store.get(document.document_id) is not None,
        )

    async def get(self, owner_id: int, document_id: int) -> DocumentInfo:
        """Return a document's metadata and whether its text is still held in memory."""
        document = (
            await self._session.execute(
                select(Document).where(
                    Document.owner_id == owner_id, Document.document_id == document_id
                )
            )
        ).scalar_one_or_none()
        if document is None:
            msg = f"Document {document_id} does not exist."
            raise NotFoundError(msg)
        text = self._store.get(document_id)
        return DocumentInfo(
            document=document,
            pages=None,
            characters=len(text) if text is not None else None,
            text_available=text is not None,
        )

    def text_of(self, document_id: int) -> str | None:
        """Return the held text (``None`` after it expired); used to generate proposals."""
        return self._store.get(document_id)
