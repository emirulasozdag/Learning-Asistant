"""Yüklenmiş dokümanları listeleme ve önizleme (eğitmen ekranı)."""

from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Document
from app.ingestion.types import IngestionError
from app.schemas.materials import ChunkPreview, DocumentOut, MaterialType

MAX_MEDIA_URL_LENGTH = 1000


def file_url(document_id: int, page: int | None = None) -> str:
    url = f"{settings.public_api_prefix}/documents/{document_id}/file"
    return f"{url}#page={page}" if page else url


def document_media_url(document: Document) -> str | None:
    """Videonun oynatma adresi: eğitmenin verdiği opak URL; yoksa None (oynatıcı gösterilmez)."""
    return document.media_url or None


def validate_media_url(url: str) -> None:
    """Harici medya adresi yalnızca https olabilir (javascript:, http: vb. reddedilir)."""
    parts = urlsplit(url)
    if (
        len(url) > MAX_MEDIA_URL_LENGTH
        or parts.scheme != "https"
        or not parts.hostname
        or any(char.isspace() or ord(char) < 32 for char in url)
    ):
        raise IngestionError(
            "Medya adresi geçerli bir https adresi olmalı (en fazla 1000 karakter)."
        )


def list_documents(db: Session, course_id: int, approved_only: bool = False) -> list[DocumentOut]:
    """Dersin dokümanları. `approved_only`: eğitmen dışındakiler onaysızları görmez (ADR-3)."""
    chunk_count = (
        select(func.count(Chunk.id)).where(Chunk.document_id == Document.id).scalar_subquery()
    )
    query = select(Document, chunk_count).where(Document.course_id == course_id)
    if approved_only:
        query = query.where(Document.approved_at.is_not(None))
    rows = db.execute(query.order_by(Document.created_at.desc(), Document.id.desc()))
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
        media_url=document_media_url(document),
    )


def chunk_previews(document: Document) -> list[ChunkPreview]:
    return [
        ChunkPreview(id=chunk.id, ordinal=chunk.ordinal, page=chunk.page, text=chunk.text)
        for chunk in document.chunks
    ]
