"""Veritabanı tabanlı iş kuyruğu (ADR-9).

Kuyruk `processing_jobs` tablosudur; ayrı bir aracı (Redis, Celery) yoktur. İş, dokümanla aynı
işlemde yazılır: doküman "işleniyor" görünüyorsa işi de vardır. Çalıştırıcı işi
`FOR UPDATE SKIP LOCKED` ile alır, böylece birden çok çalıştırıcı aynı işi almaz.

Kural: uzun adım (transkripsiyon, vektörleştirme) açık bir veritabanı işlemi içinde
çalışmaz. İş alınır ve işlem kapanır; uzun adım bittikten sonra sonuç kısa bir işlemle yazılır.

İş türleri (#27, #25, ADR-11): `transcription` dokümanın kendisini üretir; başarısız ya da iptal
olursa doküman `failed` olur ve dosyaları silinir. `frames` ve `frame_interpretation` hazır bir
dokümana kare ve betimleme ekler; başarısız ya da iptal olurlarsa doküman `ready` kalır, önceki
kareler korunur, yalnızca o işin girdi medyası silinir.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Document, ProcessingJob
from app.ingestion.documents import document_files, remove_paths

logger = logging.getLogger(__name__)

TRANSCRIPTION = "transcription"
# Medyadan slayt kareleri (#27, #25): yüklenen videonun transkripsiyonundan sonra aynı medyadan
# ya da altyazısı olan videoya sonradan eklenen medyadan. Doküman hazırdır ve hazır kalır: bu
# işin hatası ya da iptali dokümanı ve transkriptini bozmaz.
FRAMES = "frames"
# Saklanan karelerin görsel yorumlayıcıyla betimlenmesi (#25, ADR-11).
FRAME_INTERPRETATION = "frame_interpretation"
JOB_KINDS = (TRANSCRIPTION, FRAMES, FRAME_INTERPRETATION)
# Girdisi (yüklenen medya) işe ait olan türler: iş bitince ya da silinince girdi de silinir.
# Yorumlama işinin girdisi dokümanın kare klasörüdür; dokümanla yaşar.
_OWNS_INPUT = frozenset({TRANSCRIPTION, FRAMES})
ACTIVE_STATUSES = ("queued", "running")
INTERRUPTED_MESSAGE = "İşlem yarıda kaldı; dosyayı yeniden yükleyin."
INTERPRETATION_INTERRUPTED_MESSAGE = "İşlem yarıda kaldı; yorumlama yeniden başlatılabilir."
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
    """İşi başarısız/iptal olarak bitirir ve türüne göre toparlar (`_after_failure`):
    transkripsiyonda doküman `failed` olur ve dosyaları silinir; kare işlerinde doküman olduğu
    gibi kalır."""
    try:
        row = locked_job(db, job)
    except JobSuperseded:
        discard(db, job)
        return
    row.status = status
    row.error = message
    row.finished_at = func.now()
    files = _after_failure(db, row, message)
    db.commit()
    _remove(files)


def discard(db: Session, job: ClaimedJob) -> None:
    """Sonucu yazılmayacak deneme. İş satırı da yoksa (doküman silindi) işe ait girdi dosyası
    silinir; iş başka denemeye geçtiyse girdi o denemeye kalır."""
    db.rollback()
    if job.kind in _OWNS_INPUT and db.get(ProcessingJob, job.id) is None:
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


def active_job(db: Session, document_id: int, kind: str | None = None) -> ProcessingJob | None:
    """Dokümanın kuyruktaki ya da çalışan işi (verildiyse yalnızca o türden; varsa)."""
    query = select(ProcessingJob).where(
        ProcessingJob.document_id == document_id,
        ProcessingJob.status.in_(ACTIVE_STATUSES),
    )
    if kind is not None:
        query = query.where(ProcessingJob.kind == kind)
    return db.scalars(query.order_by(ProcessingJob.id)).first()


def request_cancel(db: Session, document: Document) -> bool:
    """Dokümanın süren işini iptal eder (`POST /documents/{id}/cancel`). Etkin iş yoksa False.

    Kuyruktaki iş hemen iptal olur. Çalışan iş işaretlenir; çalıştırıcı bir sonraki
    canlılık kontrolünde (en geç `job_heartbeat_interval_s`) durur. Transkripsiyonun iptali
    dokümanı başarısız yapar; kare işlerininki yapmaz (`_after_failure`). Belirli bir işi iptal
    etmek için `cancel_job`.
    """
    job = db.scalars(
        select(ProcessingJob)
        .where(
            ProcessingJob.document_id == document.id,
            ProcessingJob.status.in_(ACTIVE_STATUSES),
        )
        .order_by(ProcessingJob.id)
        .with_for_update()
    ).first()
    if job is None:
        db.rollback()
        return False
    _cancel(db, job)
    return True


def cancel_job(db: Session, job_id: int) -> bool:
    """Herhangi bir türdeki işi iptal eder (#25). İş yoksa ya da bitmişse False.

    Kuyruktaki iş hemen biter ve türüne göre toparlanır; çalışan iş işaretlenir ve çalıştırıcı
    bir sonraki canlılık kontrolünde durur. Transkripsiyonun iptali dokümanı da başarısız yapar.
    """
    job = db.get(ProcessingJob, job_id, with_for_update=True, populate_existing=True)
    if job is None or job.status not in ACTIVE_STATUSES:
        db.rollback()
        return False
    _cancel(db, job)
    return True


def _cancel(db: Session, job: ProcessingJob) -> None:
    """Kilitli, etkin işi iptal eder ve işlemi kapatır."""
    files: list[Path] = []
    if job.status == "queued":
        job.status = "cancelled"
        job.error = CANCELLED_MESSAGE
        job.finished_at = func.now()
        files = _after_failure(db, job, CANCELLED_MESSAGE)
    else:
        job.cancel_requested = True
    db.commit()
    _remove(files)


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
            message = CANCELLED_MESSAGE if job.cancel_requested else _interrupted(job.kind)
            job.status = "cancelled" if job.cancel_requested else "failed"
            job.error = message
            job.finished_at = func.now()
            files += _after_failure(db, job, message)
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


def _interrupted(kind: str) -> str:
    if kind == FRAME_INTERPRETATION:
        return INTERPRETATION_INTERRUPTED_MESSAGE
    return INTERRUPTED_MESSAGE


def _after_failure(db: Session, job: ProcessingJob, message: str) -> list[Path]:
    """Başarısız / iptal edilen işin sonucu; commit'ten sonra silinecek dosyalar.

    - transcription: doküman `failed` olur, dokümanın bütün dosyaları silinir.
    - frames: doküman hazır kalır, önceki kareler korunur; işin girdi medyası silinir (#27, #25:
      kare çıkarılamayan medya saklanmaz).
    - frame_interpretation: hiçbir şey silinmez; kareler ve önceki betimlemeler kalır.
    """
    if job.kind == FRAMES:
        return [Path(job.input_path)]
    if job.kind == FRAME_INTERPRETATION:
        return []
    return _fail_document(db, job.document_id, message)


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
    remove_paths(files)
