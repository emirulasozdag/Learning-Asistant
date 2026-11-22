"""Görsel kanıt (#26): ders videosunun orijinal karesi, türetilmiş metni ve kökeni.

Cevap üreticisi ve iddia kontrolü için kare sözleşmesi (CONTRACTS.md §4.2):

- `VisualEvidence`: bir kare. Orijinal kanıt karenin görüntüsü (`image`) ve zamanıdır
  (`t_start`–`t_end`, `t_frame`; videonun başından saniye). `derived_text` OCR'ın türettiği
  metindir (`derived_by`); üreticiye ipucu olarak gider, iddia kontrolünde kanıt sayılmaz.
  `transcript` kare ekrandayken konuşulan metindir (aynı videonun zamanlı parçaları).
- `FrameLocator`: istekteki kare referansı: video (`document_id`) ve ya kare kimliği ya da an.
- `FrameEvidenceSource`: referansları yetkili kanıta çeviren bağdaştırıcı. `StoredFrameSource`
  #24'ün `video_frames` kayıtlarından okur; `qa/service.answer_stream` isteğin doğrulanmış video
  bağlamından (#25) bununla `VisualContext` kurar ve `stream_answer(visual=…)`a verir (ADR-12).
- `VisualContext`: cevaba giren kareler ve öğrencinin durdurduğu an (varsa).

Kareler ayrı bir alıntı kimliği taşır (`frame:<kare kimliği>`); `chunks` kimlikleriyle karışmaz.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course, Document, VideoFrame
from app.ingestion.documents import frame_dir
from app.retrieval.frames import frames_overlapping, transcript_during
from app.retrieval.types import RetrievedPassage, VideoPosition
from app.schemas.materials import MaterialType
from app.schemas.sources import FrameStatus

logger = logging.getLogger(__name__)

# Kare alıntılarının kimlik öneki; parça (chunk) kimlikleri yalnızca rakamdır.
FRAME_SOURCE_PREFIX = "frame:"
# Bir cevaba giren en fazla kare (her biri görüntüyle judge'a gider; maliyet ve gecikme sınırı).
MAX_FRAMES = 4
# Judge'a gönderilecek en büyük görüntü; büyük dosya gönderilmez, iddia kontrol edilemez sayılır.
MAX_IMAGE_BYTES = 8 * 1024 * 1024
# Üreticiye giden konuşma metni sınırı (kare uzun süre ekranda kalabilir).
MAX_TRANSCRIPT_CHARS = 1500
# Durdurulan anın etrafında aranacak kareler (#102'deki bölümle aynı pencere).
MOMENT_BEFORE_S = 90.0
MOMENT_AFTER_S = 20.0

_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


@dataclass(frozen=True)
class FrameImage:
    """Karenin orijinal görüntüsü: dosyanın baytları ve türü."""

    data: bytes
    mime_type: str


@dataclass(frozen=True)
class VisualEvidence:
    """Cevaba giren bir video karesi ve kökeni."""

    frame_id: int
    course_id: int
    # Video varlığı: `material_type = "video"` olan `Document`.
    document_id: int
    document_title: str
    # Slaytın ekranda sabit kaldığı aralık ve görüntünün alındığı an (saniye).
    t_start: float
    t_end: float
    t_frame: float
    status: FrameStatus
    # Türetilmiş metin (OCR) ve onu üreten araç, ör. "tesseract/5.5.0/tur+eng". Kanıt değildir.
    derived_text: str | None
    derived_by: str
    confidence: float | None = None
    # Kare ekrandayken konuşulan transkript (aynı videonun zamanlı parçaları).
    transcript: str = ""
    # Orijinal görüntü; okunamadıysa None (bu kareye dayanan iddia kontrol edilemez sayılır).
    image: FrameImage | None = None

    @property
    def source_id(self) -> str:
        return f"{FRAME_SOURCE_PREFIX}{self.frame_id}"

    def provenance(self, image_sent: bool) -> dict:
        """Denetim kaydındaki köken: hangi videonun hangi anı, görüntü judge'a gitti mi."""
        return {
            "source_id": self.source_id,
            "frame_id": self.frame_id,
            "document_id": self.document_id,
            "t_start": self.t_start,
            "t_end": self.t_end,
            "t_frame": self.t_frame,
            "status": self.status,
            "derived_by": self.derived_by,
            "image_sent": image_sent,
        }

    def as_passage(self) -> RetrievedPassage:
        """Alıntı doğrulaması ve `Citation` için kareyi parça biçiminde gösterir. Metni türetilmiş
        metindir; judge'a gitmez (görsel iddialar yalnızca görüntüyle kontrol edilir)."""
        return RetrievedPassage(
            source_id=self.source_id,
            document_id=self.document_id,
            document_title=self.document_title,
            text=self.derived_text or "",
            score=0.0,
            t_start=self.t_start,
            t_end=self.t_end,
        )


@dataclass(frozen=True)
class FrameLocator:
    """İstekteki kare referansı: video ve ya saklanan kare (`frame_id`) ya da an (`time_s`)."""

    document_id: int
    frame_id: int | None = None
    time_s: float | None = None

    def __post_init__(self) -> None:
        if (self.frame_id is None) == (self.time_s is None):
            raise ValueError("FrameLocator: frame_id ya da time_s'ten tam olarak biri verilmeli.")


@dataclass
class VisualContext:
    """Cevaba giren kareler (en çok `MAX_FRAMES`) ve öğrencinin durdurduğu an."""

    frames: list[VisualEvidence] = field(default_factory=list)
    focus: VideoPosition | None = None

    def focus_frame(self) -> VisualEvidence | None:
        """Durdurulan anda ekranda olan kare; an yoksa ya da o anda kare yoksa None."""
        if self.focus is None:
            return None
        return next(
            (
                frame
                for frame in self.frames
                if frame.document_id == self.focus.document_id
                and frame.t_start <= self.focus.time_s < frame.t_end
            ),
            None,
        )


class FrameEvidenceSource(Protocol):
    """Kare referanslarını yetkili görsel kanıta çeviren bağdaştırıcı.

    Uygulama yalnızca isteğin dersindeki onaylı ve hazır video dokümanlarının karelerini döndürür;
    yetkisiz ya da bulunamayan referansı atlar (erişim hatasını isteği doğrulayan katman verir).
    """

    def load(self, locators: Sequence[FrameLocator]) -> list[VisualEvidence]: ...


class StoredFrameSource:
    """#24'ün `video_frames` tablosundan kare kanıtı (ADR-10). Erişim `frame_search` ile aynı:
    dersin onaylı (`approved_at`) ve `ready` video dokümanı."""

    def __init__(self, db: Session, course: Course) -> None:
        self._db = db
        self._course = course

    def load(self, locators: Sequence[FrameLocator]) -> list[VisualEvidence]:
        evidence: list[VisualEvidence] = []
        seen: set[int] = set()
        for locator in locators:
            document = self._video(locator.document_id)
            if document is None:
                logger.info("Kare referansı atlandı: video %s erişilebilir değil", locator)
                continue
            if locator.frame_id is not None:
                frame = self._db.get(VideoFrame, locator.frame_id)
                frames = [frame] if frame is not None and frame.document_id == document.id else []
            else:
                assert locator.time_s is not None
                frames = frames_overlapping(
                    self._db, document.id, locator.time_s, locator.time_s, course_id=self._course.id
                )
            for frame in frames:
                if frame.id not in seen and len(evidence) < MAX_FRAMES:
                    seen.add(frame.id)
                    evidence.append(self._evidence(frame, document))
        return evidence

    def moment(
        self,
        video: VideoPosition,
        before_s: float = MOMENT_BEFORE_S,
        after_s: float = MOMENT_AFTER_S,
        frame_id: int | None = None,
    ) -> VisualContext:
        """Durdurulan anın etrafındaki kareler: o anda ekrandaki kare önce, sonra ana yakınlığa
        göre (en çok `MAX_FRAMES`). Video erişilebilir değilse kare yok, an korunur.

        `frame_id`: öğrencinin baktığı kare (#25'te doğrulanmış `VideoRef.frame_id`). Bu videonun
        karesiyse her zaman alınır ve an ona odaklanır: kare durdurulan anda ekranda değilse
        (doğrulamadaki 1 sn pay) odak karenin başına alınır. Başka videonun karesi yok sayılır.
        """
        document = self._video(video.document_id)
        if document is None:
            return VisualContext(focus=video)
        start = max(video.time_s - before_s, 0.0)
        frames = frames_overlapping(
            self._db, document.id, start, video.time_s + after_s, course_id=self._course.id
        )
        selected = self._db.get(VideoFrame, frame_id) if frame_id is not None else None
        focus = video
        if selected is not None and selected.document_id == document.id:
            if all(frame.id != selected.id for frame in frames):
                frames.append(selected)
            if not selected.t_start <= video.time_s < selected.t_end:
                focus = VideoPosition(video.document_id, selected.t_start)
        else:
            selected = None

        def distance(frame: VideoFrame) -> float:
            if selected is not None and frame.id == selected.id:
                return -1.0
            if frame.t_start <= video.time_s < frame.t_end:
                return 0.0
            return min(abs(frame.t_start - video.time_s), abs(frame.t_end - video.time_s))

        nearest = sorted(frames, key=lambda frame: (distance(frame), frame.ordinal))[:MAX_FRAMES]
        nearest.sort(key=lambda frame: frame.ordinal)
        return VisualContext(
            frames=[self._evidence(frame, document) for frame in nearest], focus=focus
        )

    def _video(self, document_id: int) -> Document | None:
        return self._db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.course_id == self._course.id,
                Document.material_type == MaterialType.VIDEO.value,
                Document.approved_at.is_not(None),
                Document.status == "ready",
            )
        )

    def _evidence(self, frame: VideoFrame, document: Document) -> VisualEvidence:
        transcript = " ".join(chunk.text for chunk in transcript_during(self._db, frame))
        return VisualEvidence(
            frame_id=frame.id,
            course_id=document.course_id,
            document_id=document.id,
            document_title=document.title,
            t_start=frame.t_start,
            t_end=frame.t_end,
            t_frame=frame.t_frame,
            status=frame.status,  # type: ignore[arg-type]
            derived_text=frame.text,
            derived_by=frame.extractor,
            confidence=frame.confidence,
            transcript=_clip(transcript, MAX_TRANSCRIPT_CHARS),
            image=read_frame_image(
                Path(frame.image_path), frame_dir(document.course_id, document.id)
            ),
        )


def read_frame_image(path: Path, allowed_dir: Path) -> FrameImage | None:
    """Kare görüntüsünü okur. Dosya yoksa, dokümanın kare klasörü dışındaysa, çok büyükse ya da
    PNG/JPEG değilse None: görüntü olmadan bu kareye dayanan iddia kontrol edilemez sayılır."""
    try:
        if not path.is_file() or not path.resolve().is_relative_to(allowed_dir.resolve()):
            return None
        if path.stat().st_size > MAX_IMAGE_BYTES:
            logger.warning("Kare görüntüsü çok büyük, gönderilmedi: %s", path.name)
            return None
        data = path.read_bytes()
    except OSError as exc:
        logger.warning("Kare görüntüsü okunamadı (%s): %s", path.name, exc)
        return None
    mime_type = next((mime for magic, mime in _SIGNATURES if data.startswith(magic)), None)
    return FrameImage(data, mime_type) if mime_type else None


def format_frames(frames: dict[str, VisualEvidence], focus: VideoPosition | None) -> str:
    """Üreticiye giden `<kareler>` bloğu: etiket, video, zaman, durum, türetilmiş metin ve
    konuşma. Durdurulan an verildiyse o anda ekrandaki karenin etiketi (ya da kare olmadığı)."""
    blocks = []
    for label, frame in frames.items():
        derived = frame.derived_text or ""
        blocks.append(
            f'<kare etiket="{label}" video="{frame.document_title}" '
            f'zaman="{clock(frame.t_start)}–{clock(frame.t_end)}" durum="{frame.status}" '
            f'görüntü="{"var" if frame.image else "yok"}">\n'
            f'<türetilmiş_metin kaynak="{frame.derived_by}">{derived}</türetilmiş_metin>\n'
            f"<konuşma>{frame.transcript}</konuşma>\n</kare>"
        )
    text = "<kareler>\n" + "\n".join(blocks) + "\n</kareler>"
    if focus is not None:
        on_screen = next(
            (
                label
                for label, frame in frames.items()
                if frame.document_id == focus.document_id
                and frame.t_start <= focus.time_s < frame.t_end
            ),
            None,
        )
        text += (
            f'\n<durdurulan_an zaman="{clock(focus.time_s)}" '
            f'ekrandaki_kare="{on_screen or "yok"}"/>'
        )
    return text


def clock(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + " …"
