from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Document, VideoFrame
from app.ingestion.documents import document_media_url, file_url
from app.ingestion.rendering import find_highlights, is_pdf, pdf_on_disk
from app.retrieval.frames import frames_overlapping
from app.schemas.common import PG_INT_MAX
from app.schemas.materials import MaterialType
from app.schemas.sources import FrameRef, SourceAlternative, SourceDetail

MAX_ALTERNATIVES = 3
# Kare alıntılarının kimlik öneki (#26 `generation/visual.FRAME_SOURCE_PREFIX` ile aynı); parça
# kimlikleri yalnızca rakamdır.
FRAME_SOURCE_PREFIX = "frame:"


def chunk_id(source_id: str) -> int | None:
    """Alıntı kimliğinin (chunk id) sayısı; geçerli bir parça kimliği değilse None.

    Yalnızca ASCII rakamlar kabul edilir (`"١٢".isdigit()` da doğrudur) ve değer veritabanı
    aralığında olmalıdır; yoksa sorgu 500 ile düşer.
    """
    # Uzunluk sınırı `int()`'ten önce: çok uzun rakam dizisi Python'da da hata verir.
    if not (0 < len(source_id) <= 10 and source_id.isascii() and source_id.isdigit()):
        return None
    value = int(source_id)
    return value if 1 <= value <= PG_INT_MAX else None


def find_chunk(db: Session, source_id: str) -> Chunk | None:
    """Alıntı kimliğinin (chunk id) parçası. Erişimi çağıran denetler (`chunk.course_id`)."""
    value = chunk_id(source_id)
    return db.get(Chunk, value) if value is not None else None


def find_frame(db: Session, source_id: str) -> VideoFrame | None:
    """Kare alıntısının (`frame:<kare kimliği>`, #26) karesi. Erişimi çağıran denetler."""
    if not source_id.startswith(FRAME_SOURCE_PREFIX):
        return None
    value = chunk_id(source_id.removeprefix(FRAME_SOURCE_PREFIX))
    return db.get(VideoFrame, value) if value is not None else None


def frame_source_detail(frame: VideoFrame, document: Document) -> SourceDetail:
    """Kare alıntısının görünümü (#25): videonun o aralığı ve karenin kendisi (`frames[0]`).

    `text` karenin türetilmiş (OCR) metnidir, okunamadıysa boş; orijinal kanıt görüntüdür.
    """
    return SourceDetail(
        source_id=f"{FRAME_SOURCE_PREFIX}{frame.id}",
        course_id=document.course_id,
        document_id=document.id,
        document_title=document.title,
        material_type=MaterialType(document.material_type),
        text=frame.text or "",
        t_start=frame.t_start,
        t_end=frame.t_end,
        media_url=document_media_url(document),
        frames=[to_frame_ref(frame)],
    )


def source_detail(db: Session, chunk: Chunk) -> SourceDetail:
    """Parça metni, sayfası, PDF'te sayfa görüntüsü ve işaretler; videoda doküman karşılıkları
    ve parçanın aralığında ekranda olan kareler (#24)."""
    source_id = str(chunk.id)
    document = chunk.document
    pdf = is_pdf(document) and chunk.page is not None
    # Dosya diskte yoksa sayfa görüntüsü verilmez; arayüz alıntı metnini gösterir (#105).
    page_view = pdf and pdf_on_disk(document)
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
            if page_view
            else None
        ),
        highlights=find_highlights(document, chunk.page, chunk.text) if page_view else [],
        alternatives=(
            document_alternatives(db, chunk) if document.material_type == MaterialType.VIDEO else []
        ),
        frames=(
            [
                to_frame_ref(frame)
                for frame in frames_overlapping(db, document.id, chunk.t_start, chunk.t_end)
            ]
            if chunk.t_start is not None and chunk.t_end is not None
            else []
        ),
    )


def to_frame_ref(frame: VideoFrame) -> FrameRef:
    """Kare kaydı → API görünümü; görüntü dokümanın erişim kuralıyla sunulur (ADR-10)."""
    return FrameRef(
        frame_id=frame.id,
        document_id=frame.document_id,
        t_start=frame.t_start,
        t_end=frame.t_end,
        t_frame=frame.t_frame,
        image_url=(
            f"{settings.public_api_prefix}/documents/{frame.document_id}/frames/{frame.id}.png"
        ),
        status=frame.status,
        text=frame.text,
        confidence=frame.confidence,
        extractor=frame.extractor,
        description=frame.description,
        description_model=frame.description_model,
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
