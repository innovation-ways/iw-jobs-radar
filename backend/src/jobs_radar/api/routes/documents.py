"""Document upload endpoints (document 07, section 3). The original is processed in memory."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartParser

from jobs_radar.adapters.documents.extract import MAX_BYTES
from jobs_radar.api.deps import get_document_service, get_session
from jobs_radar.core.errors import InputValidationError
from jobs_radar.domain.enums import LOCAL_OWNER_ID
from jobs_radar.schemas.document import DocumentRead
from jobs_radar.services.documents import DocumentInfo, DocumentService

router = APIRouter(tags=["documents"])

Service = Annotated[DocumentService, Depends(get_document_service)]
Session = Annotated[AsyncSession, Depends(get_session)]

# Starlette spools an upload to a temporary file once it exceeds 1 MiB. A CV must never reach the
# disk (ADR-010), so the spool limit is raised above the largest accepted file: bigger uploads are
# refused by the size check, not written out.
MultiPartParser.spool_max_size = MAX_BYTES + 1024
_MULTIPART_OVERHEAD = 64 * 1024


def document_read(info: DocumentInfo) -> DocumentRead:
    """Map a document and its transient facts to the API model."""
    document = info.document
    return DocumentRead(
        document_id=document.document_id,
        sha256=document.sha256,
        mime_type=document.mime_type,
        byte_size=document.byte_size,
        extraction_status=document.extraction_status,
        extraction_version=document.extraction_version,
        pages=info.pages,
        characters=info.characters,
        text_available=info.text_available,
        created_at=document.created_at,
    )


@router.post("/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(request: Request, service: Service, session: Session) -> DocumentRead:
    """Accept one file, extract its text in memory and discard the original."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES + _MULTIPART_OVERHEAD:
        msg = "The file is too large."
        raise InputValidationError(msg, details={"error_class": "too_large"})
    form = await request.form(max_files=1, max_fields=5, max_part_size=MAX_BYTES + 1024)
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        msg = "Send the CV as a 'file' part of a multipart request."
        raise InputValidationError(msg)
    data = await upload.read(MAX_BYTES + 1)
    info = await service.upload(LOCAL_OWNER_ID, upload.filename or "", upload.content_type, data)
    await session.commit()
    return document_read(info)


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(document_id: int, service: Service) -> DocumentRead:
    """Return safe metadata: the status and whether the text is still held in memory."""
    return document_read(await service.get(LOCAL_OWNER_ID, document_id))
