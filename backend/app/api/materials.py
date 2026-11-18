from pathlib import Path
from typing import Annotated, BinaryIO

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.api.deps import DbSession, get_course_for
from app.api.errors import ApiError
from app.auth.dependencies import AuthUser, CurrentUser, not_found_error, require_course_role
from app.core.config import settings
from app.db.models import Document, ProcessingJob, VideoFrame
from app.ingestion.documents import (
    chunk_previews,
    document_files,
    frame_dir,
    list_documents,
    remove_paths,
    to_document_out,
    validate_upload_fields,
)
from app.ingestion.frame_interpretation import interpreter_configured
from app.ingestion.media import add_frame_media, create_media_document, is_media
from app.ingestion.pipeline import MAX_UPLOAD_BYTES, IngestionError, ingest_document
from app.ingestion.rendering import page_image_path, remove_cached_pages
from app.jobs.queue import (
    FRAME_INTERPRETATION,
    active_job,
    cancel_job,
    enqueue,
    request_cancel,
)
from app.schemas.common import Role
from app.schemas.materials import ChunkPreview, DocumentOut, MaterialType, ProcessingJobOut
from app.schemas.sources import FrameRef
from app.sources.lookup import to_frame_ref

router = APIRouter(tags=["materials"])

_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".vtt": "text/vtt",
}


@router.post(
    "/courses/{course_id}/materials",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_material(
    course_id: int,
    user: AuthUser,
    db: DbSession,
    material_type: Annotated[MaterialType, Form()],
    file: Annotated[UploadFile, File()],
    declaration: Annotated[bool, Form()] = False,
    title: Annotated[str | None, Form()] = None,
    media_url: Annotated[str | None, Form()] = None,
) -> DocumentOut:
    """FR-01..02: onaylı materyali yükle → parse → temizle → parçala → vektörleştir.

    `.vtt` altyazısı video olarak kaydedilir; `media_url` (https) videonun harici oynatma
    adresidir. Yalnızca dersin eğitmeni yükler ve beyanı (`declaration`) işaretler: "Bu
    materyali bu derste kullanma yetkim var; aktif sınav içeriği değil." Yükleme onay
    sayılır (ADR-3). Cevaptaki `report`, hattın her adımında ne olduğunu gösterir.

    Ders videosu/sesi (.mp4 .webm .mkv .mov .mp3 .m4a .wav) yalnızca sunucuda transkripsiyon
    açıksa (`TRANSCRIPTION_MODEL`) kabul edilir: dosya diske akıtılır, doküman `processing`
    olarak 201 döner (rapor yok) ve transkripsiyon kuyruktaki iş olarak sürer (ADR-9).
    Kapalıyken 422. Boyut sınırı istek gövdesi okunurken uygulanır (`app/core/limits.py`).
    """
    course = get_course_for(db, user, course_id, "instructor")
    if not declaration:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Yüklemeden önce materyali bu derste kullanma yetkiniz olduğunu ve aktif sınav "
            "içeriği olmadığını onaylayın.",
            "validation_error",
        )
    filename = file.filename or "dosya"
    if is_media(filename):
        try:
            document, media_path = create_media_document(
                db,
                course,
                filename,
                file.file,
                title=title,
                media_url=media_url,
                approved_by=user.id,
            )
        except IngestionError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        return to_document_out(document, 0)
    try:
        validate_upload_fields(filename, title)
        document, report = ingest_document(
            db,
            course,
            filename=filename,
            content=_read_limited(file.file, MAX_UPLOAD_BYTES),
            material_type=material_type,
            title=title,
            media_url=media_url,
            approved_by=user.id,
        )
    except IngestionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    result = to_document_out(document, len(document.chunks))
    result.report = report
    return result


@router.get("/courses/{course_id}/materials", response_model=list[DocumentOut])
def list_materials(course_id: int, user: AuthUser, db: DbSession) -> list[DocumentOut]:
    """Dersin yüklenmiş dokümanları ve parça sayıları (dersin üyeleri)."""
    get_course_for(db, user, course_id)
    return list_documents(db, course_id, approved_only=user.roles.get(course_id) != "instructor")


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkPreview])
def document_chunks(document_id: int, user: AuthUser, db: DbSession) -> list[ChunkPreview]:
    """Sistemin dokümandan çıkardığı parçalar (sayfa numaralarıyla)."""
    return chunk_previews(_get_document(db, user, document_id))


@router.get("/documents/{document_id}/frames", response_model=list[FrameRef])
def document_frames(document_id: int, user: AuthUser, db: DbSession) -> list[FrameRef]:
    """Videodan çıkarılan kareler, zamana göre; okunamayanlar durumlarıyla birlikte (#24).

    Kare çıkarılmamış dokümanda (PDF, altyazıyla yüklenen video, özellik kapalı) boş liste.
    """
    document = _get_document(db, user, document_id)
    frames = db.scalars(
        select(VideoFrame).where(VideoFrame.document_id == document.id).order_by(VideoFrame.ordinal)
    )
    return [to_frame_ref(frame) for frame in frames]


@router.post("/documents/{document_id}/frames", response_model=DocumentOut)
def add_frames_from_video(
    document_id: int,
    user: AuthUser,
    db: DbSession,
    file: Annotated[UploadFile, File()],
) -> DocumentOut:
    """Altyazısıyla yüklenmiş videoya video dosyasını ekler; slayt kareleri çıkarılır (#27).

    Transkript yeniden çıkarılmaz ve doküman hazır kalır; kareler kuyruktaki iş bitince görünür
    (`frames_processing`). Yeniden eklemek önceki karelerin yerini alır. Video olmayan ya da
    hazır olmayan dokümanda, süren iş varken ve kare çıkarma kapalıyken 409 `frames_unavailable`.
    """
    document = _get_document(db, user, document_id, "instructor")
    if document.material_type != MaterialType.VIDEO.value or document.status != "ready":
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "Slayt kareleri yalnızca hazır bir ders videosuna eklenebilir.",
            "frames_unavailable",
        )
    # Dosya yazılırken doküman satırı kilitli kalır (#25): eşzamanlı ikinci ekleme beklenir,
    # depolama temizliği aynı adlı eski bir artığı bu sırada silemez (`jobs/retention.py`).
    _lock_document(db, document.id)
    if active_job(db, document.id) is not None:
        db.rollback()
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "Bu video için süren bir işlem var; bitince tekrar dene.",
            "frames_unavailable",
        )
    try:
        add_frame_media(db, document, file.filename or "video", file.file)
    except IngestionError as exc:
        raise ApiError(status.HTTP_409_CONFLICT, str(exc), "frames_unavailable") from exc
    db.refresh(document)
    frames = db.scalar(
        select(func.count(VideoFrame.id)).where(VideoFrame.document_id == document.id)
    )
    return to_document_out(document, len(document.chunks), frames or 0, frames_processing=True)


@router.get("/documents/{document_id}/frames/{frame_id}.png")
def document_frame_image(
    document_id: int, frame_id: int, user: AuthUser, db: DbSession
) -> FileResponse:
    """Karenin orijinal görüntüsü (#24). Başka dokümanın karesi ya da dosyası olmayan kare 404."""
    document = _get_document(db, user, document_id)
    frame = db.get(VideoFrame, frame_id)
    image = Path(frame.image_path) if frame is not None else None
    if (
        frame is None
        or frame.document_id != document.id
        or image is None
        or not image.is_file()
        or not image.resolve().is_relative_to(frame_dir(document.course_id, document.id).resolve())
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kare görüntüsü yok")
    # Sayfa görüntüsü gibi: oturumla yetkilendirilir, tarayıcı her seferinde sunucuya sorar.
    return FileResponse(
        image, media_type="image/png", headers={"Cache-Control": "private, no-cache"}
    )


@router.delete("/documents/{document_id}/frames/{frame_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_frame(document_id: int, frame_id: int, user: AuthUser, db: DbSession) -> None:
    """Tek bir kareyi ve görüntüsünü siler (yalnızca eğitmen, #25).

    Kare yanlışlıkla gizli bir içerik yakaladıysa (ör. öğrenci listesi, açık bir pencere) eğitmen
    onu kaldırır; transkript ve diğer kareler etkilenmez. Soru kayıtlarındaki kare kimliği kalır,
    görüntüsü artık sunulmaz. Başka dokümanın karesi 404 `frame_not_found`.
    """
    document = _get_document(db, user, document_id, "instructor")
    frame = db.get(VideoFrame, frame_id)
    if frame is None or frame.document_id != document.id:
        raise not_found_error("frame_not_found")
    image = Path(frame.image_path)
    db.delete(frame)
    db.commit()
    if image.resolve().is_relative_to(frame_dir(document.course_id, document.id).resolve()):
        image.unlink(missing_ok=True)


@router.post(
    "/documents/{document_id}/frames/interpret",
    response_model=ProcessingJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def interpret_frames(document_id: int, user: AuthUser, db: DbSession) -> ProcessingJobOut:
    """Videonun karelerini görsel yorumlayıcıyla betimleme işini kuyruğa alır (eğitmen, #25).

    Sunucuda yorumlayıcı yoksa 409 `interpreter_not_configured`; karesi yoksa 409 `no_frames`;
    dokümanda süren bir iş (kare çıkarma, yorumlama) varsa 409 `job_already_active`. Başarısız ya
    da iptal edilen yorumlama bu uçla yeniden başlatılır.
    """
    document = _get_document(db, user, document_id, "instructor")
    if not interpreter_configured():
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "Bu sunucuda kare yorumlayıcısı yapılandırılmamış.",
            "interpreter_not_configured",
        )
    # Aynı doküman için eşzamanlı iki istek iki iş açmasın: doküman satırı kilitlenir.
    _lock_document(db, document.id)
    if active_job(db, document.id) is not None:
        db.rollback()
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "Bu videonun kareleri şu anda işleniyor.",
            "job_already_active",
        )
    if (
        db.scalar(select(VideoFrame.id).where(VideoFrame.document_id == document.id).limit(1))
        is None
    ):
        db.rollback()
        raise ApiError(status.HTTP_409_CONFLICT, "Bu videonun karesi yok.", "no_frames")
    job = enqueue(db, FRAME_INTERPRETATION, document, frame_dir(document.course_id, document.id))
    db.commit()
    db.refresh(job)
    return _job_out(job)


@router.get("/documents/{document_id}/jobs", response_model=list[ProcessingJobOut])
def document_jobs(document_id: int, user: AuthUser, db: DbSession) -> list[ProcessingJobOut]:
    """Dokümanın uzun süren işleri (transkripsiyon, kare çıkarma, yorumlama), eskiden yeniye
    (yalnızca eğitmen, #25)."""
    document = _get_document(db, user, document_id, "instructor")
    jobs = db.scalars(
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document.id)
        .order_by(ProcessingJob.id)
    )
    return [_job_out(job) for job in jobs]


@router.post("/documents/{document_id}/jobs/{job_id}/cancel", response_model=ProcessingJobOut)
def cancel_document_job(
    document_id: int, job_id: int, user: AuthUser, db: DbSession
) -> ProcessingJobOut:
    """Dokümanın bir işini iptal eder (yalnızca eğitmen, #25).

    Kuyruktaki iş hemen `cancelled` olur; çalışan iş işaretlenir (`cancel_requested`) ve birkaç
    saniye içinde durur. Transkripsiyonun iptali dokümanı `failed` yapar; kare işlerinin iptali
    dokümanı `ready` bırakır. Başka dokümanın işi 404 `job_not_found`; bitmiş iş 409
    `job_not_active`.
    """
    document = _get_document(db, user, document_id, "instructor")
    job = db.get(ProcessingJob, job_id)
    if job is None or job.document_id != document.id:
        raise not_found_error("job_not_found")
    if not cancel_job(db, job.id):
        raise ApiError(status.HTTP_409_CONFLICT, "Bu iş zaten bitmiş.", "job_not_active")
    db.refresh(job)
    return _job_out(job)


def _lock_document(db: DbSession, document_id: int) -> None:
    """Doküman satırını işlem sonuna kadar kilitler (`FOR UPDATE`)."""
    db.execute(select(Document.id).where(Document.id == document_id).with_for_update())


def _job_out(job: ProcessingJob) -> ProcessingJobOut:
    return ProcessingJobOut(
        id=job.id,
        document_id=job.document_id,
        kind=job.kind,  # type: ignore[arg-type]
        status=job.status,  # type: ignore[arg-type]
        attempts=job.attempts,
        max_attempts=settings.job_max_attempts,
        cancel_requested=job.cancel_requested,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, user: AuthUser, db: DbSession) -> None:
    """Dokümanı, parçalarını, dosyalarını, sayfa ve kare görüntülerini siler (yalnızca eğitmen).

    İşlenen dokümanın işi de silinir; çalışan iş sonucu yazmadan biter.
    """
    document = _get_document(db, user, document_id, "instructor")
    files = document_files(document.course_id, document.id, document.file_path)
    db.delete(document)
    db.commit()
    remove_paths(files)
    remove_cached_pages(document_id)


@router.post("/documents/{document_id}/cancel", response_model=DocumentOut)
def cancel_processing(document_id: int, user: AuthUser, db: DbSession) -> DocumentOut:
    """Süren işlemi (transkripsiyon ya da kare çıkarma, #27) iptal eder (yalnızca eğitmen).

    Transkripsiyonda kuyruktaki iş hemen iptal olur ve doküman `failed` döner; çalışan iş durması
    için işaretlenir, doküman birkaç saniye içinde `failed` olur. Kare işinin iptali dokümanı
    bozmaz: hazır kalır, önceki kareler korunur. Süren iş yoksa 409.
    """
    document = _get_document(db, user, document_id, "instructor")
    if not request_cancel(db, document):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "Bu doküman şu anda işlenmiyor.",
            "document_not_processing",
        )
    db.refresh(document)
    return to_document_out(document, len(document.chunks))


@router.get("/documents/{document_id}/pages/{page}.png")
def document_page_image(document_id: int, page: int, user: AuthUser, db: DbSession) -> FileResponse:
    """PDF sayfasının görüntüsü (kaynak görüntüleyici için)."""
    image = page_image_path(_get_document(db, user, document_id), page)
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sayfa görüntüsü yok")
    # Oturumla yetkilendirilir: tarayıcı her seferinde sunucuya sorar (ETag ile 304), çıkıştan
    # ya da hesap değişiminden sonra önbellekten gösterilmez.
    return FileResponse(
        image, media_type="image/png", headers={"Cache-Control": "private, no-cache"}
    )


@router.get("/documents/{document_id}/file")
def document_file(document_id: int, user: AuthUser, db: DbSession) -> FileResponse:
    """Orijinal dosya. PDF tarayıcıda `#page=N` ile ilgili sayfada açılır."""
    document = _get_document(db, user, document_id)
    path = Path(document.file_path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dosya bulunamadı")
    return FileResponse(
        path,
        media_type=_MEDIA_TYPES.get(path.suffix, "application/octet-stream"),
        filename=document.filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store"},
    )


def _read_limited(source: BinaryIO, limit: int) -> bytes:
    """Dosyayı sınırı aşınca durarak okur; sınırı aşan dosya belleğe alınmaz."""
    content = source.read(limit + 1)
    if len(content) > limit:
        raise IngestionError(f"Dosya {limit // (1024 * 1024)} MB sınırını aşıyor.")
    return content


def _get_document(db: DbSession, user: CurrentUser, document_id: int, *roles: Role) -> Document:
    """Kullanıcının üye olduğu dersin dokümanı; değilse 404 (varlık sızdırılmaz).

    Onaysız doküman (ADR-3, B'ye geçilirse) ve hazır olmayan (işleniyor / başarısız) doküman
    yalnızca eğitmene görünür.
    """
    document = db.get(Document, document_id)
    if document is None:
        raise not_found_error("document_not_found")
    # Sıra: üyelik → onaysız dokümanın görünürlüğü → işlem için rol.
    role = require_course_role(user, document.course_id, not_found="document_not_found")
    if (document.approved_at is None or document.status != "ready") and role != "instructor":
        raise not_found_error("document_not_found")
    require_course_role(user, document.course_id, *roles, not_found="document_not_found")
    return document
