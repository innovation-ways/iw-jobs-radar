"""API contracts for uploaded documents (document 07, section 3). Content never appears here."""

from datetime import datetime
from typing import Literal

from jobs_radar.schemas.common import StrictModel


class DocumentRead(StrictModel):
    """Safe metadata of an uploaded document; the original and its text are not returned."""

    document_id: int
    sha256: str
    mime_type: str
    byte_size: int
    extraction_status: Literal["uploaded", "extracted", "needs_ocr", "failed"]
    extraction_version: str | None
    pages: int | None
    characters: int | None
    text_available: bool
    created_at: datetime
