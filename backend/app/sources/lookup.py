from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk
from app.ingestion.documents import document_media_url, file_url
from app.ingestion.rendering import find_highlights, is_pdf
from app.schemas.materials import MaterialType
from app.schemas.sources import SourceDetail


def find_chunk(db: Session, source_id: str) -> Chunk | None:
    """Alıntı kimliğinin (chunk id) parçası. Erişimi çağıran denetler (`chunk.course_id`)."""
    if not source_id.isdigit() or len(source_id) > 18:
        return None
    return db.get(Chunk, int(source_id))


def source_detail(chunk: Chunk) -> SourceDetail:
    """Parça metni, sayfası, PDF'te sayfa görüntüsü ve işaretler."""
    source_id = str(chunk.id)
    document = chunk.document
    pdf = is_pdf(document) and chunk.page is not None
    return SourceDetail(
        source_id=source_id,
        course_id=document.course_id,
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
