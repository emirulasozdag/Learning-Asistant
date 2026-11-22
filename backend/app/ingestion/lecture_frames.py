"""Transkripsiyon işinin kare adımı: çıkar, OCR ile oku, vektörleştir, kaydet (#24, ADR-10).

Kare adımı transkripti bozmaz: video çözülemezse ya da Tesseract çalışmazsa uyarı yazılır, kare
kaydedilmez ve doküman yine hazır olur. Tek bir karenin okunamaması o kareyi `unreadable` yapar.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import cast, func, literal
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.orm import Session

from app.db.models import Course, Document, VideoFrame
from app.db.text_search import ts_config
from app.embeddings.base import Embedder
from app.ingestion.documents import remove_paths
from app.ingestion.frames import FrameExtractionError, extract_frames
from app.ingestion.ocr import (
    OcrError,
    OcrResult,
    extractor_identity,
    read_image,
    tesseract_languages,
)
from app.jobs.queue import JobCancelled

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FrameDraft:
    """Kaydedilmeye hazır kare: zamanlar, geçici görüntü dosyası, OCR sonucu ve vektörü."""

    ordinal: int
    t_start: float
    t_end: float
    t_frame: float
    image_name: str
    ocr: OcrResult
    extractor: str
    vector: list[float] | None


def read_lecture_frames(
    media_path: Path,
    out_dir: Path,
    course_language: str,
    duration_s: float | None,
    embedder: Embedder,
    should_stop: Callable[[], bool] = lambda: False,
) -> list[FrameDraft]:
    """Medyadan kareleri `out_dir`e çıkarır ve okur. Kare adımı yapılamazsa boş liste
    (uyarıyla); iptalde `JobCancelled`."""
    languages = tesseract_languages(course_language)
    try:
        extractor = extractor_identity(languages)
        extracted = extract_frames(media_path, out_dir, should_stop)
    except (FrameExtractionError, OcrError) as exc:
        logger.warning(
            "%s: kareler çıkarılamadı (%s); transkript kareler olmadan kaydedilecek",
            media_path.name,
            exc,
        )
        remove_paths([out_dir])
        return []

    # Videonun zaman çizelgesi dokümanın süresidir (çoğunlukla altyazının sonu). mp4 daha uzunsa
    # (ör. OCW'nin kapanış ekranı) sonrasında başlayan kare sıfır uzunlukta bir aralığa sıkışır:
    # hiçbir ana ve transkripte denk gelmez ama aranabilir kalırdı (#29). Bu kareler alınmaz.
    outside = [f for f in extracted if duration_s is not None and f.t_start >= duration_s]
    if outside:
        logger.info(
            "%s: videonun süresinden (%.1f sn) sonra başlayan %d kare atlandı",
            media_path.name,
            duration_s,
            len(outside),
        )
        remove_paths([frame.image_path for frame in outside])
        extracted = [frame for frame in extracted if frame not in outside]

    results: list[OcrResult] = []
    for frame in extracted:
        if should_stop():
            raise JobCancelled(media_path.name)
        try:
            results.append(read_image(frame.image_path, languages))
        except OcrError as exc:
            logger.warning("%s: %d. kare okunamadı (%s)", media_path.name, frame.ordinal, exc)
            results.append(OcrResult(status="unreadable", text=None, confidence=None))

    texts = [result.text for result in results if result.text]
    vectors = iter(embedder.embed_passages(texts) if texts else [])
    drafts = []
    for frame, result in zip(extracted, results, strict=True):
        t_end = min(frame.t_end, duration_s) if duration_s else frame.t_end
        t_frame = min(frame.t_frame, t_end)
        drafts.append(
            FrameDraft(
                ordinal=frame.ordinal,
                t_start=min(frame.t_start, t_frame),
                t_end=t_end,
                t_frame=t_frame,
                image_name=frame.image_path.name,
                ocr=result,
                extractor=extractor,
                vector=next(vectors) if result.text else None,
            )
        )
    return drafts


def add_frames(
    db: Session,
    course: Course,
    document: Document,
    drafts: list[FrameDraft],
    image_dir: Path,
    embedder: Embedder,
) -> None:
    """Kareleri `video_frames`e ekler; görüntüler `image_dir`de olmalıdır. Metinsiz karelerin
    vektörü ve kelime indeksi boştur (aranmaz)."""
    config = cast(literal(ts_config(course.language)), REGCONFIG)
    db.add_all(
        VideoFrame(
            document_id=document.id,
            course_id=course.id,
            ordinal=draft.ordinal,
            t_start=draft.t_start,
            t_end=draft.t_end,
            t_frame=draft.t_frame,
            image_path=str(image_dir / draft.image_name),
            status=draft.ocr.status,
            text=draft.ocr.text,
            confidence=draft.ocr.confidence,
            extractor=draft.extractor,
            search_vector=func.to_tsvector(config, draft.ocr.text) if draft.ocr.text else None,
            embedding=draft.vector,
            embedding_model=embedder.identity if draft.vector is not None else None,
        )
        for draft in drafts
    )
