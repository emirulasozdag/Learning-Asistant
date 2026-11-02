from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Document
from app.ingestion.documents import document_media_url, file_url
from app.ingestion.rendering import find_highlights, is_pdf
from app.schemas.materials import MaterialType
from app.schemas.sources import SourceAlternative, SourceDetail

MAX_ALTERNATIVES = 3


def find_chunk(db: Session, source_id: str) -> Chunk | None:
    """Alıntı kimliğinin (chunk id) parçası. Erişimi çağıran denetler (`chunk.course_id`)."""
    if not source_id.isdigit() or len(source_id) > 18:
        return None
    return db.get(Chunk, int(source_id))


def source_detail(db: Session, chunk: Chunk) -> SourceDetail:
    """Parça metni, sayfası, PDF'te sayfa görüntüsü ve işaretler; videoda doküman karşılıkları."""
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
        alternatives=(
            document_alternatives(db, chunk) if document.material_type == MaterialType.VIDEO else []
        ),
    )


def document_alternatives(db: Session, chunk: Chunk) -> list[SourceAlternative]:
    """Video parçasıyla aynı içeriği taşıyan doküman parçaları (#19).

    Aynı dersin onaylı ve hazır, video olmayan dokümanlarından; aynı embedder'ın vektörleriyle
    kosinüs benzerliği arama kapısının eşiğinden (`retrieval_min_similarity`) yüksek olanlar.
    Eşik geçilmezse boş: zayıf benzerlik "aynı içerik" diye gösterilmez.
    """
    if chunk.embedding is None or chunk.embedding_model is None:
        return []
    similarity = (1 - Chunk.embedding.cosine_distance(chunk.embedding)).label("similarity")
    rows = db.execute(
        select(Chunk, Document, similarity)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.course_id == chunk.course_id,
            Document.course_id == chunk.course_id,
            Document.approved_at.is_not(None),
            Document.status == "ready",
            Document.material_type != MaterialType.VIDEO.value,
            Chunk.embedding.is_not(None),
            Chunk.embedding_model == chunk.embedding_model,
        )
        .order_by(similarity.desc(), Chunk.id)
        .limit(MAX_ALTERNATIVES)
    )
    return [
        SourceAlternative(
            source_id=str(match.id),
            document_id=document.id,
            document_title=document.title,
            material_type=MaterialType(document.material_type),
            page=match.page,
            similarity=round(float(score), 4),
        )
        for match, document, score in rows
        if score >= settings.retrieval_min_similarity
    ]
