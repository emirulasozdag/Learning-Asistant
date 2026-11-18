"""Altyazısı olmayan ders videosu/sesi: yükleme kaydı ve transkripsiyon işi (ADR-6, ADR-9).

Akış: yükleme isteği medyayı diske akıtır, dokümanı `status="processing"` olarak ve
transkripsiyon işini kuyruğa aynı işlemde kaydeder, 201 döner. İşi çalıştırıcı
(`app/jobs/worker.py`) alır. Bitince transkript WebVTT olarak saklanır (dokümanın dosyası
odur), medya silinir; zamanlı parçalar mevcut altyazı yolundaki gibi üretilir. Kalıcı hatada
doküman `failed` olur ve nedeni `error`a yazılır.

Süreç iş sürerken durursa (yeniden başlatma, çökme) medya diskte kalır; iş yeniden kuyruğa
alınır (`jobs.queue.recover_stale`), eğitmenin dosyayı yeniden yüklemesi gerekmez.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import delete, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Course, Document, VideoFrame
from app.embeddings.base import Embedder
from app.embeddings.provider import get_embedder
from app.ingestion.chunking import chunk_timed_segments
from app.ingestion.cleaning import normalize_timed_segments
from app.ingestion.documents import (
    frame_dir,
    remove_paths,
    validate_media_url,
    validate_upload_fields,
)
from app.ingestion.lecture_frames import FrameDraft, add_frames, read_lecture_frames
from app.ingestion.parsers.vtt_parser import write_vtt
from app.ingestion.pipeline import add_chunks
from app.ingestion.transcribe import Transcriber, TranscriptionError
from app.ingestion.types import ChunkDraft, IngestionError, RawSegment
from app.jobs.queue import (
    FRAMES,
    TRANSCRIPTION,
    ClaimedJob,
    JobCancelled,
    JobSuperseded,
    enqueue,
    locked_job,
)
from app.schemas.materials import MaterialType

logger = logging.getLogger(__name__)

MEDIA_EXTENSIONS = frozenset({".mp4", ".webm", ".mkv", ".mov", ".mp3", ".m4a", ".wav"})
COPY_CHUNK_BYTES = 1024 * 1024
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
    """Medyayı diske parça parça kopyalar (belleğe okunmaz); `processing` doküman ve
    transkripsiyon işini kaydeder.

    Kapalıysa, boyut sınırı aşılırsa ya da dosya boşsa `IngestionError`; kayıt ve dosya kalmaz.
    """
    if not settings.transcription_model:
        raise IngestionError(TRANSCRIPTION_DISABLED_MESSAGE)
    validate_upload_fields(filename, title)
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
        enqueue(db, TRANSCRIPTION, document, path)
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    db.refresh(document)
    return document, path


FRAMES_DISABLED_MESSAGE = (
    "Bu sunucuda slayt karesi çıkarma kapalı (FRAME_EXTRACTION=ocr değil); video dosyası eklenemez."
)
# Kareler görüntüden çıkar: ses dosyasında kare yoktur.
VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".mkv", ".mov"})


def add_frame_media(db: Session, document: Document, filename: str, source: BinaryIO) -> Path:
    """Altyazısı olan (hazır) videoya medya dosyası ekler ve kare işini kuyruğa alır (#27).

    Transkript yeniden çıkarılmaz; medyadan yalnızca slayt kareleri alınır. Doküman hazır kalır.
    Kapalıysa, video değilse, boyut aşılırsa ya da dosya boşsa `IngestionError`; dosya kalmaz.
    """
    if settings.frame_extraction != "ocr":
        raise IngestionError(FRAMES_DISABLED_MESSAGE)
    extension = Path(filename).suffix.lower()
    if extension not in VIDEO_EXTENSIONS:
        raise IngestionError(
            "Slayt kareleri için video dosyası gerekir (.mp4, .webm, .mkv ya da .mov)."
        )
    # Dokümanın kendi dosyasından (altyazı) ayrı ad; silinirken `document_files` yine bulur.
    path = settings.upload_dir / str(document.course_id) / f"{document.id}.frames{extension}"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        size = _copy_limited(source, path, settings.max_media_bytes)
        if size == 0:
            raise IngestionError("Dosya boş.")
        enqueue(db, FRAMES, document, path)
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return path


def frames_job(
    session_factory: Callable[[], Session],
    job: ClaimedJob,
    should_stop: Callable[[], bool],
    embedder: Embedder | None = None,
) -> None:
    """Kare işi (#27): medyadan slayt karelerini çıkarır, OCR ile okur, eskilerinin yerine yazar.

    Transkripte, parçalara ve dokümanın durumuna dokunmaz. Uzun adımlar açık işlem olmadan
    çalışır (`transcription_job` ile aynı kural). Hiç kare çıkmazsa (video çözülemedi, Tesseract
    yok) mevcut kareler korunur ve iş başarısız biter; doküman hazır kalır (`queue.FRAMES`).
    """
    with session_factory() as db:
        document = db.get(Document, job.document_id)
        if document is None:
            raise JobSuperseded(job.id)
        course_id = document.course_id
        duration_s = document.duration_s
        language = db.get(Course, course_id).language  # type: ignore[union-attr]

    embedder = embedder or get_embedder()
    staging = frame_dir(course_id, job.document_id, staging=True)
    remove_paths([staging])
    try:
        frames = read_lecture_frames(
            job.input_path, staging, language, duration_s, embedder, should_stop
        )
        if should_stop():
            raise JobCancelled(job.id)
        if not frames:
            raise IngestionError("Videodan slayt karesi çıkarılamadı.")
        _save_frames(session_factory, job, frames, staging, embedder)
    finally:
        remove_paths([staging])
    job.input_path.unlink(missing_ok=True)


def _save_frames(
    session_factory: Callable[[], Session],
    job: ClaimedJob,
    frames: list[FrameDraft],
    staging: Path,
    embedder: Embedder,
) -> None:
    """Kareleri tek kısa işlemle yazar: eskiler silinir, yeniler eklenir."""
    with session_factory() as db:
        row = locked_job(db, job)
        if row.cancel_requested:
            raise JobCancelled(job.id)
        document = db.get(Document, job.document_id)
        course = db.get(Course, document.course_id) if document else None
        if document is None or course is None:
            raise JobSuperseded(job.id)
        images = frame_dir(course.id, document.id)
        previous = images.with_name(f"{document.id}.previous")
        row.status = "succeeded"
        row.error = None
        row.finished_at = func.now()
        db.execute(delete(VideoFrame).where(VideoFrame.document_id == document.id))
        # Eski görüntüler commit başarılı olana kadar kenarda bekler; hata olursa geri gelir.
        remove_paths([previous])
        if images.exists():
            images.rename(previous)
        try:
            staging.rename(images)
            add_frames(db, course, document, frames, images, embedder)
            db.commit()
        except Exception:
            remove_paths([images])
            if previous.exists():
                previous.rename(images)
            raise
        remove_paths([previous])


def _copy_limited(source: BinaryIO, path: Path, limit: int) -> int:
    size = 0
    with path.open("wb") as out:
        while chunk := source.read(COPY_CHUNK_BYTES):
            size += len(chunk)
            if size > limit:
                raise IngestionError(f"Medya dosyası {limit // (1024 * 1024)} MB sınırını aşıyor.")
            out.write(chunk)
    return size


def transcription_job(
    session_factory: Callable[[], Session],
    job: ClaimedJob,
    transcriber: Transcriber,
    should_stop: Callable[[], bool],
    embedder: Embedder | None = None,
) -> None:
    """Transkripsiyon işi: transkript → zamanlı parçalar → vektörler → (açıksa) kareler →
    doküman `ready`.

    Uzun adımlar (transkripsiyon, kare çıkarma, OCR, vektörleştirme) açık bir veritabanı işlemi
    olmadan çalışır; önce gereken alanlar okunup oturum kapanır, sonuç sonda kısa bir işlemle
    yazılır. Kalıcı hatada `TranscriptionError`/`IngestionError`, iptalde `JobCancelled`, doküman
    ya da iş silindiyse `JobSuperseded` yükselir; dokümanın durumunu çalıştırıcı yazar.

    Kareler (`FRAME_EXTRACTION=ocr`, ADR-10) medya silinmeden önce geçici klasöre çıkarılır;
    sonuç yazılırken dokümanın kare klasörüne taşınır. Kare adımı yapılamazsa transkript yine
    kaydedilir (`read_lecture_frames`).
    """
    with session_factory() as db:
        document = db.get(Document, job.document_id)
        if document is None:  # Doküman silindi (iş de onunla silinir).
            raise JobSuperseded(job.id)
        course_id = document.course_id
        language = db.get(Course, course_id).language  # type: ignore[union-attr]

    segments, duration_s, warnings = transcriber.transcribe(
        job.input_path, language, should_stop=should_stop
    )
    for warning in warnings:
        logger.warning("Doküman %s: %s", job.document_id, warning)
    cleaned, _ = normalize_timed_segments(segments)
    embedder = embedder or get_embedder()
    drafts = chunk_timed_segments(cleaned, embedder)
    if not drafts:
        raise TranscriptionError("Medyada konuşma bulunamadı.")
    vectors = embedder.embed_passages([draft.text for draft in drafts])
    if should_stop():
        raise JobCancelled(job.id)

    staging = frame_dir(course_id, job.document_id, staging=True)
    remove_paths([staging])  # Önceki denemeden kalmış olabilir.
    try:
        frames: list[FrameDraft] = []
        if settings.frame_extraction == "ocr":
            frames = read_lecture_frames(
                job.input_path, staging, language, duration_s, embedder, should_stop
            )
            if should_stop():
                raise JobCancelled(job.id)
        _save_transcript(
            session_factory,
            job,
            transcriber,
            cleaned,
            duration_s,
            drafts,
            vectors,
            frames,
            staging,
            embedder,
        )
    finally:
        remove_paths([staging])
    job.input_path.unlink(missing_ok=True)


def _save_transcript(
    session_factory: Callable[[], Session],
    job: ClaimedJob,
    transcriber: Transcriber,
    cleaned: list[RawSegment],
    duration_s: float,
    drafts: list[ChunkDraft],
    vectors: list[list[float]],
    frames: list[FrameDraft],
    staging: Path,
    embedder: Embedder,
) -> None:
    """Sonucu tek kısa işlemle yazar: transkript dosyası, parçalar, kareler, doküman `ready`."""
    with session_factory() as db:
        row = locked_job(db, job)
        if row.cancel_requested:
            raise JobCancelled(job.id)
        document = db.get(Document, job.document_id)
        course = db.get(Course, document.course_id) if document else None
        if document is None or course is None:
            raise JobSuperseded(job.id)
        vtt_path = settings.upload_dir / str(course.id) / f"{document.id}.vtt"
        images = frame_dir(course.id, document.id)
        document.file_path = str(vtt_path)
        document.filename = f"{document.title[:290]}.vtt"
        document.page_count = 0
        document.duration_s = duration_s
        document.transcript_source = "asr"
        document.transcript_model = transcriber.identity
        document.status = "ready"
        document.error = None
        row.status = "succeeded"
        row.error = None
        row.finished_at = func.now()
        try:
            write_vtt(vtt_path, cleaned)
            add_chunks(db, course, document, drafts, vectors, embedder)
            if frames:
                remove_paths([images])
                staging.rename(images)
                add_frames(db, course, document, frames, images, embedder)
            db.commit()
        except Exception:
            remove_paths([vtt_path, images])
            raise
