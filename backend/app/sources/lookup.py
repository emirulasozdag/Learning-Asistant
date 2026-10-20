from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk
from app.ingestion.documents import document_media_url, file_url
from app.ingestion.rendering import find_highlights, is_pdf
from app.schemas.materials import MaterialType
from app.schemas.sources import SourceDetail


def get_source(db: Session, source_id: str) -> SourceDetail | None:
    """Alıntı kimliğinden (chunk id): parça metni, sayfası, PDF'te sayfa görüntüsü ve işaretler."""
    if not source_id.isdigit():
        return None
    chunk = db.get(Chunk, int(source_id))
    if chunk is None:
        return None
    document = chunk.document
    pdf = is_pdf(document) and chunk.page is not None
    return SourceDetail(
        source_id=source_id,
        document_id=document.id,
        document_title=document.title,
        material_type=MaterialType(document.material_type),
        text=chunk.text,
        page=chunk.page,
        t_start=chunk.t_start,
        t_end=chunk.t_end,
        media_url=(
            document_media_url(document)
            if document.material_type == MaterialType.VIDEO
            else file_url(document.id, chunk.page if pdf else None)
        ),
        page_image_url=(
            f"{settings.public_api_prefix}/documents/{document.id}/pages/{chunk.page}.png"
            if pdf
            else None
        ),
        highlights=find_highlights(document, chunk.page, chunk.text) if pdf else [],
    )
