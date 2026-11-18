"""Kare yorumlama işi (#25, ADR-11): saklanan karelerin görsel yorumlayıcıyla betimlenmesi.

Bu modül yorumlayıcının arayüzünü (`FrameInterpreter`), işin yaşam döngüsünü (kuyruk, iptal,
yeniden deneme; ADR-9) ve sonucun saklanmasını tanımlar. Yorumlayıcının kendisi (yerel ya da
hosted görsel dil modeli) #24'ün işidir ve `INTERPRETERS`a adıyla kaydedilir; `FRAME_INTERPRETER`
o adı seçer. Ad boşsa ya da kayıtlı değilse yorumlama kapalıdır: iş kuyruğa alınmaz.

Kurallar:
- Girdi yalnızca dokümanın kare klasöründeki orijinal kare görüntüsüdür (klasör dışı yol
  okunmaz) ve karenin bağlamı (OCR metni, karenin aralığında konuşulan transkript).
- Betimleme türetilmiş metindir: `VideoFrame.description`a yazılır, orijinal kanıt değildir,
  aranmaz ve alıntılanmaz (kanıt kuralları #26). Uydurma yerine `None` döndürülür.
- Yorumlayıcının veri rotası (yerel/hosted) ADR-5 ve ADR-8'e tabidir; kayıt eden iş bunu belgeler.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Course, Document, VideoFrame
from app.ingestion.documents import frame_dir
from app.jobs.queue import ClaimedJob, JobCancelled, JobSuperseded, locked_job
from app.retrieval.frames import transcript_during

logger = logging.getLogger(__name__)

# Saklanan betimlemenin en büyük uzunluğu (karakter); fazlası kesilir.
MAX_DESCRIPTION_CHARS = 4000
NOT_CONFIGURED_MESSAGE = "Kare yorumlayıcısı yapılandırılmamış."


class InterpretationError(Exception):
    """Kalıcı yorumlama hatası (model yüklenemedi, kimlik bilgisi yok); kısa Türkçe neden taşır.
    İş yeniden denenmeden başarısız olur. Geçici hatalar (ağ) başka bir istisna olarak yükselir
    ve deneme hakkı varsa iş yeniden denenir."""


@dataclass(frozen=True)
class FrameContext:
    """Yorumlayıcıya karenin görüntüsüyle birlikte verilen bağlam."""

    frame_id: int
    document_id: int
    # Slaytın ekranda kaldığı aralık ve görüntünün alındığı an (saniye).
    t_start: float
    t_end: float
    t_frame: float
    # OCR'ın okuduğu yazı (türetilmiş); okunamadıysa None.
    ocr_text: str | None
    # Karenin aralığında konuşulan transkript.
    transcript: str
    # Dersin dili ("tr" | "en").
    language: str


class FrameInterpreter(Protocol):
    # Kareye yazılan yorumlayıcı kimliği, ör. "<model>/<sürüm>".
    identity: str

    def interpret(self, image_path: Path, context: FrameContext) -> str | None:
        """Karenin betimlemesi; güvenilir bir betimleme verilemiyorsa None (uydurma yok).

        Kalıcı hatada `InterpretationError`.
        """
        ...


# Ad → yorumlayıcı üreticisi. Gerçek yorumlayıcılar burada kaydedilir (#24).
INTERPRETERS: dict[str, Callable[[], FrameInterpreter]] = {}


def interpreter_configured() -> bool:
    return bool(settings.frame_interpreter) and settings.frame_interpreter in INTERPRETERS


def get_interpreter() -> FrameInterpreter:
    factory = INTERPRETERS.get(settings.frame_interpreter) if settings.frame_interpreter else None
    if factory is None:
        raise InterpretationError(NOT_CONFIGURED_MESSAGE)
    return factory()


@dataclass(frozen=True)
class _Input:
    image_path: Path
    context: FrameContext


def interpretation_job(
    session_factory: Callable[[], Session],
    job: ClaimedJob,
    interpreter: FrameInterpreter,
    should_stop: Callable[[], bool],
) -> None:
    """`frame_interpretation` işi: dokümanın her karesini yorumlar, sonucu kısa bir işlemle yazar.

    Model çağrıları açık bir veritabanı işlemi olmadan yapılır. İş sürerken silinen kare atlanır.
    İptalde `JobCancelled`, doküman ya da iş silindiyse `JobSuperseded`; kalıcı hatada
    `InterpretationError`. İşin durumunu çalıştırıcı yazar; hata ya da iptalde kareler ve önceki
    betimlemeler değişmez.
    """
    inputs = _read_inputs(session_factory, job)
    results: dict[int, str | None] = {}
    for item in inputs:
        if should_stop():
            raise JobCancelled(job.id)
        results[item.context.frame_id] = _clean(
            interpreter.interpret(item.image_path, item.context)
        )
    if should_stop():
        raise JobCancelled(job.id)

    with session_factory() as db:
        row = locked_job(db, job)
        if row.cancel_requested:
            raise JobCancelled(job.id)
        frames = db.scalars(
            select(VideoFrame).where(
                VideoFrame.document_id == job.document_id, VideoFrame.id.in_(list(results))
            )
        ).all()
        for frame in frames:
            frame.description = results[frame.id]
            frame.description_model = interpreter.identity[:200]
        row.status = "succeeded"
        row.error = None
        row.finished_at = func.now()
        db.commit()
    logger.info("Doküman %s: %d kare yorumlandı", job.document_id, len(frames))


def _read_inputs(session_factory: Callable[[], Session], job: ClaimedJob) -> list[_Input]:
    """Dokümanın kareleri ve bağlamları; görüntüsü kare klasörünün dışında ya da diskte olmayan
    kare yorumlanmaz."""
    with session_factory() as db:
        document = db.get(Document, job.document_id)
        course = db.get(Course, document.course_id) if document else None
        if document is None or course is None:
            raise JobSuperseded(job.id)
        root = frame_dir(document.course_id, document.id).resolve()
        frames = db.scalars(
            select(VideoFrame)
            .where(VideoFrame.document_id == document.id)
            .order_by(VideoFrame.ordinal)
        ).all()
        inputs = []
        for frame in frames:
            image = Path(frame.image_path).resolve()
            if not image.is_relative_to(root) or not image.is_file():
                logger.warning("Kare %s: görüntü kare klasöründe yok; yorumlanmadı", frame.id)
                continue
            transcript = " ".join(chunk.text for chunk in transcript_during(db, frame))
            inputs.append(
                _Input(
                    image,
                    FrameContext(
                        frame_id=frame.id,
                        document_id=document.id,
                        t_start=frame.t_start,
                        t_end=frame.t_end,
                        t_frame=frame.t_frame,
                        ocr_text=frame.text,
                        transcript=transcript,
                        language=course.language,
                    ),
                )
            )
        return inputs


def _clean(description: str | None) -> str | None:
    if description is None:
        return None
    text = description.strip()[:MAX_DESCRIPTION_CHARS]
    return text or None
