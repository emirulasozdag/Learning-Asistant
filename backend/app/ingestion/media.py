"""Altyazısı olmayan ders videosu/sesi: yükleme kaydı ve arka plan transkripsiyonu (ADR-6).

Akış: yükleme isteği medyayı diske akıtır, dokümanı `status="processing"` olarak kaydeder ve
201 döner; `run_transcription` arka planda (FastAPI BackgroundTasks) çalışır. Bitince transkript
WebVTT olarak saklanır (dokümanın dosyası odur), medya silinir; zamanlı parçalar mevcut altyazı
yolundaki gibi üretilir. Hata olursa doküman `failed` olur ve nedeni `error`a yazılır.

Uyarı: süren iş sunucu sürecinin içinde koşar. docker-compose'taki `--reload`, kod değişince
süreci yeniden başlatır ve süren işi öldürür; açılışta `fail_interrupted_documents` takılı
kalan dokümanları `failed` yapar, eğitmen dosyayı yeniden yükler.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Course, Document
from app.embeddings.base import Embedder
from app.embeddings.provider import get_embedder
from app.ingestion.chunking import chunk_timed_segments
from app.ingestion.cleaning import normalize_timed_segments
from app.ingestion.documents import validate_media_url
from app.ingestion.parsers.vtt_parser import write_vtt
from app.ingestion.pipeline import add_chunks
from app.ingestion.transcribe import Transcriber, TranscriptionError
from app.ingestion.types import IngestionError
from app.schemas.materials import MaterialType

logger = logging.getLogger(__name__)

MEDIA_EXTENSIONS = frozenset({".mp4", ".webm", ".mkv", ".mov", ".mp3", ".m4a", ".wav"})
COPY_CHUNK_BYTES = 1024 * 1024
INTERRUPTED_MESSAGE = "İşlem yarıda kaldı; dosyayı yeniden yükleyin."
TRANSCRIPTION_DISABLED_MESSAGE = (
    "Bu sunucuda transkripsiyon kapalı; videonun altyazısını (.vtt) yükleyin."
)


def is_media(filename: str) -> bool:
    return Path(filename).suffix.lower() in MEDIA_EXTENSIONS


def create_media_document(
    db: Session,
    course: Course,
    filename: str,
    source: BinaryIO,
    title: str | None,
    media_url: str | None,
    approved_by: int,
) -> tuple[Document, Path]:
    """Medyayı diske parça parça kopyalar (belleğe okunmaz) ve `processing` doküman kaydeder.

    Kapalıysa, boyut sınırı aşılırsa ya da dosya boşsa `IngestionError`; kayıt ve dosya kalmaz.
    """
    if not settings.transcription_model:
        raise IngestionError(TRANSCRIPTION_DISABLED_MESSAGE)
    if media_url is not None:
        validate_media_url(media_url)
    extension = Path(filename).suffix.lower()
    document = Document(
        course_id=course.id,
        title=title or Path(filename).stem,
        material_type=MaterialType.VIDEO.value,
        filename=Path(filename).name,
        file_path="",
        media_url=media_url,
        approved_by=approved_by,
        approved_at=func.now(),
        status="processing",
    )
    db.add(document)
    db.flush()

    path = settings.upload_dir / str(course.id) / f"{document.id}{extension}"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        size = _copy_limited(source, path, settings.max_media_bytes)
        if size == 0:
            raise IngestionError("Dosya boş.")
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    db.refresh(document)
    return document, path


def _copy_limited(source: BinaryIO, path: Path, limit: int) -> int:
    size = 0
    with path.open("wb") as out:
        while chunk := source.read(COPY_CHUNK_BYTES):
            size += len(chunk)
            if size > limit:
                raise IngestionError(f"Medya dosyası {limit // (1024 * 1024)} MB sınırını aşıyor.")
            out.write(chunk)
    return size


def run_transcription(
    session_factory: Callable[[], Session],
    document_id: int,
    media_path: Path,
    transcriber: Transcriber,
    embedder: Embedder | None = None,
) -> None:
    """Arka plan işi: transkripsiyon → zamanlı parçalar → vektörler; kendi oturumunu açar.

    Başarıda doküman `ready`, transkript WebVTT dosyası dokümanın dosyası olur. Hatada `failed`
    ve Türkçe kısa neden; parça yazılmaz. Her durumda medya dosyası silinir.
    """
    try:
        with session_factory() as db:
            try:
                _transcribe_document(db, document_id, media_path, transcriber, embedder)
            except Exception as exc:
                db.rollback()
                if isinstance(exc, TranscriptionError | IngestionError):
                    message = str(exc)
                else:
                    logger.exception("Transkripsiyon beklenmeyen bir hatayla bitti")
                    message = "Beklenmeyen bir hata oluştu."
                _mark_failed(db, document_id, message)
    finally:
        media_path.unlink(missing_ok=True)


def _transcribe_document(
    db: Session,
    document_id: int,
    media_path: Path,
    transcriber: Transcriber,
    embedder: Embedder | None,
) -> None:
    document = db.get(Document, document_id)
    if document is None:  # Süren işin dokümanı silindi.
        return
    course = db.get(Course, document.course_id)
    assert course is not None
    segments, duration_s, warnings = transcriber.transcribe(media_path, course.language)
    for warning in warnings:
        logger.warning("Doküman %s: %s", document_id, warning)
    cleaned, _ = normalize_timed_segments(segments)
    embedder = embedder or get_embedder()
    drafts = chunk_timed_segments(cleaned, embedder)
    if not drafts:
        raise TranscriptionError("Medyada konuşma bulunamadı.")
    vectors = embedder.embed_passages([draft.text for draft in drafts])

    vtt_path = settings.upload_dir / str(course.id) / f"{document.id}.vtt"
    document.file_path = str(vtt_path)
    document.filename = f"{document.title[:290]}.vtt"
    document.page_count = 0
    document.duration_s = duration_s
    document.transcript_source = "asr"
    document.transcript_model = transcriber.identity
    document.status = "ready"
    document.error = None
    try:
        write_vtt(vtt_path, cleaned)
        add_chunks(db, course, document, drafts, vectors, embedder)
        db.commit()
    except Exception:
        vtt_path.unlink(missing_ok=True)
        raise


def _mark_failed(db: Session, document_id: int, message: str) -> None:
    document = db.get(Document, document_id)
    if document is None:
        return
    document.status = "failed"
    document.error = message
    document.file_path = ""
    db.commit()


def fail_interrupted_documents(session_factory: Callable[[], Session]) -> int:
    """Açılışta `processing`de kalmış dokümanları `failed` yapar; artık medya dosyalarını siler."""
    with session_factory() as db:
        stuck = db.scalars(select(Document).where(Document.status == "processing")).all()
        for document in stuck:
            document.status = "failed"
            document.error = INTERRUPTED_MESSAGE
            course_dir = settings.upload_dir / str(document.course_id)
            for leftover in course_dir.glob(f"{document.id}.*"):
                leftover.unlink(missing_ok=True)
        db.commit()
        return len(stuck)
