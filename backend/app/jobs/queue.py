"""Veritabanı tabanlı iş kuyruğu (ADR-9).

Kuyruk `processing_jobs` tablosudur; ayrı bir aracı (Redis, Celery) yoktur. İş, dokümanla aynı
işlemde yazılır: doküman "işleniyor" görünüyorsa işi de vardır. Çalıştırıcı işi
`FOR UPDATE SKIP LOCKED` ile alır, böylece birden çok çalıştırıcı aynı işi almaz.

Kural: uzun adım (transkripsiyon, vektörleştirme) açık bir veritabanı işlemi içinde
çalışmaz. İş alınır ve işlem kapanır; uzun adım bittikten sonra sonuç kısa bir işlemle yazılır.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Document, ProcessingJob
from app.ingestion.documents import document_files

logger = logging.getLogger(__name__)

TRANSCRIPTION = "transcription"
ACTIVE_STATUSES = ("queued", "running")
INTERRUPTED_MESSAGE = "İşlem yarıda kaldı; dosyayı yeniden yükleyin."
CANCELLED_MESSAGE = "İşlem eğitmen tarafından iptal edildi."
UNEXPECTED_MESSAGE = "Beklenmeyen bir hata oluştu."
RETRY_MESSAGE = "Önceki deneme yarıda kaldı; yeniden deneniyor."


class JobCancelled(Exception):
    """İş iptal edildi; sonuç yazılmaz."""


class JobSuperseded(Exception):
    """İş ya da dokümanı silindi veya iş başka bir denemeye geçti; bu deneme sonuç yazmaz."""


@dataclass(frozen=True)
class ClaimedJob:
    id: int
    kind: str
    document_id: int
    input_path: Path
    attempts: int


def enqueue(db: Session, kind: str, document: Document, input_path: Path) -> ProcessingJob:
    """İşi kuyruğa ekler. Çağıran, dokümanla birlikte aynı işlemde commit eder."""
    job = ProcessingJob(
        kind=kind,
        document_id=document.id,
        input_path=str(input_path),
        status="queued",
        attempts=0,
    )
    db.add(job)
    return job


def claim_next(db: Session) -> ClaimedJob | None:
    """Sıradaki işi `running` yapar ve döndürür; iş yoksa None. İşlem kapatılarak döner."""
    job = db.scalars(
        select(ProcessingJob)
        .where(ProcessingJob.status == "queued")
        .order_by(ProcessingJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job is None:
        db.rollback()
        return None
    job.status = "running"
    job.attempts += 1
    job.started_at = func.now()
    job.heartbeat_at = func.now()
    db.commit()
    return ClaimedJob(job.id, job.kind, job.document_id, Path(job.input_path), job.attempts)


def heartbeat(db: Session, job: ClaimedJob) -> bool:
    """Çalışan işin canlılık zamanını yeniler. Devam etmemeli ise False (iptal ya da iş yok)."""
    row = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job.id,
            ProcessingJob.status == "running",
            ProcessingJob.attempts == job.attempts,
        )
        .values(heartbeat_at=func.now())
        .returning(ProcessingJob.cancel_requested)
    ).first()
    db.commit()
    return row is not None and not row.cancel_requested


def locked_job(db: Session, job: ClaimedJob) -> ProcessingJob:
    """Bu denemenin iş satırı (kilitli); yoksa ya da başka denemeye geçtiyse `JobSuperseded`."""
    row = db.get(ProcessingJob, job.id, with_for_update=True)
    if row is None or row.status != "running" or row.attempts != job.attempts:
        raise JobSuperseded(job.id)
    return row


def settle(db: Session, job: ClaimedJob, status: str, message: str) -> None:
    """İşi başarısız/iptal olarak bitirir: doküman `failed` olur, dokümanın dosyaları silinir."""
    try:
        row = locked_job(db, job)
    except JobSuperseded:
        discard(db, job)
        return
    row.status = status
    row.error = message
    row.finished_at = func.now()
    files = _fail_document(db, row.document_id, message)
    db.commit()
    _remove(files)


def discard(db: Session, job: ClaimedJob) -> None:
    """Sonucu yazılmayacak deneme. İş satırı da yoksa (doküman silindi) girdi dosyası silinir;
    iş başka denemeye geçtiyse girdi o denemeye kalır."""
    db.rollback()
    if db.get(ProcessingJob, job.id) is None:
        job.input_path.unlink(missing_ok=True)
    db.rollback()


def retry_later(db: Session, job: ClaimedJob, message: str) -> bool:
    """Deneme hakkı varsa işi yeniden kuyruğa alır (girdi korunur); yoksa başarısız bitirir."""
    if job.attempts >= settings.job_max_attempts:
        settle(db, job, "failed", UNEXPECTED_MESSAGE)
        return False
    try:
        row = locked_job(db, job)
    except JobSuperseded:
        db.rollback()
        return False
    row.status = "queued"
    row.error = message
    db.commit()
    return True


def request_cancel(db: Session, document: Document) -> bool:
    """Dokümanın süren işini iptal eder. Etkin iş yoksa False.

    Kuyruktaki iş hemen iptal olur. Çalışan iş işaretlenir; çalıştırıcı bir sonraki
    canlılık kontrolünde (en geç `job_heartbeat_interval_s`) durur ve dokümanı başarısız yapar.
    """
    job = db.scalars(
        select(ProcessingJob)
        .where(
            ProcessingJob.document_id == document.id,
            ProcessingJob.status.in_(ACTIVE_STATUSES),
        )
        .with_for_update()
    ).first()
    if job is None:
        db.rollback()
        return False
    files: list[Path] = []
    if job.status == "queued":
        job.status = "cancelled"
        job.error = CANCELLED_MESSAGE
        job.finished_at = func.now()
        files = _fail_document(db, document.id, CANCELLED_MESSAGE)
    else:
        job.cancel_requested = True
    db.commit()
    _remove(files)
    return True


def recover_stale(db: Session) -> tuple[int, int]:
    """Sahipsiz kalan işleri toparlar: (yeniden kuyruğa alınan, başarısız biten) sayısı.

    Canlılık zamanı `job_stale_after_s`'ten eski çalışan iş, çalıştırıcısı öldüğü (süreç
    yeniden başladı, çöktü) için sahipsizdir: deneme hakkı varsa yeniden kuyruğa alınır, yoksa
    başarısız olur. İşi olmayan "işleniyor" dokümanlar (ADR-9'dan önceki yüklemeler) başarısız
    olur. Birden çok çalıştırıcı aynı anda çağırabilir.
    """
    cutoff = func.now() - timedelta(seconds=settings.job_stale_after_s)
    stale = db.scalars(
        select(ProcessingJob)
        .where(ProcessingJob.status == "running", ProcessingJob.heartbeat_at < cutoff)
        .with_for_update(skip_locked=True)
    ).all()
    requeued, failed = 0, 0
    files: list[Path] = []
    for job in stale:
        if job.cancel_requested or job.attempts >= settings.job_max_attempts:
            message = CANCELLED_MESSAGE if job.cancel_requested else INTERRUPTED_MESSAGE
            job.status = "cancelled" if job.cancel_requested else "failed"
            job.error = message
            job.finished_at = func.now()
            files += _fail_document(db, job.document_id, message)
            failed += 1
        else:
            job.status = "queued"
            job.error = RETRY_MESSAGE
            requeued += 1
    has_active_job = exists().where(
        ProcessingJob.document_id == Document.id,
        ProcessingJob.status.in_(ACTIVE_STATUSES),
    )
    orphans = db.scalars(
        select(Document)
        .where(Document.status == "processing", ~has_active_job)
        .with_for_update(skip_locked=True)
    ).all()
    for document in orphans:
        files += _fail_document(db, document.id, INTERRUPTED_MESSAGE)
        failed += 1
    db.commit()
    _remove(files)
    if requeued or failed:
        logger.warning("Yarıda kalan işler: %d yeniden kuyrukta, %d başarısız", requeued, failed)
    return requeued, failed


def _fail_document(db: Session, document_id: int, message: str) -> list[Path]:
    """Dokümanı `failed` yapar; commit'ten sonra silinecek dosyalarını döndürür."""
    document = db.get(Document, document_id)
    if document is None:
        return []
    files = document_files(document.course_id, document.id, document.file_path)
    document.status = "failed"
    document.error = message
    document.file_path = ""
    return files


def _remove(files: list[Path]) -> None:
    for path in files:
        path.unlink(missing_ok=True)
