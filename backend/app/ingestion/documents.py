"""Yüklenmiş dokümanları listeleme ve önizleme (eğitmen ekranı)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Document
from app.schemas.materials import ChunkPreview, DocumentOut, MaterialType


def file_url(document_id: int, page: int | None = None) -> str:
    url = f"{settings.public_api_prefix}/documents/{document_id}/file"
    return f"{url}#page={page}" if page else url


def list_documents(db: Session, course_id: int) -> list[DocumentOut]:
    chunk_count = (
        select(func.count(Chunk.id)).where(Chunk.document_id == Document.id).scalar_subquery()
    )
    rows = db.execute(
        select(Document, chunk_count)
        .where(Document.course_id == course_id)
        .order_by(Document.created_at.desc(), Document.id.desc())
    )
    return [to_document_out(document, count) for document, count in rows]


def to_document_out(document: Document, chunk_count: int) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        course_id=document.course_id,
        title=document.title,
        material_type=MaterialType(document.material_type),
        filename=document.filename,
        page_count=document.page_count,
        chunk_count=chunk_count,
        created_at=document.created_at,
        file_url=file_url(document.id),
        duration_s=document.duration_s,
        media_url=document.media_url,
    )


def chunk_previews(document: Document) -> list[ChunkPreview]:
    return [
        ChunkPreview(id=chunk.id, ordinal=chunk.ordinal, page=chunk.page, text=chunk.text)
        for chunk in document.chunks
    ]
