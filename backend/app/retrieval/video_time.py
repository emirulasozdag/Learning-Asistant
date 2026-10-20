from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course, Document
from app.retrieval.types import RetrievedPassage, VideoPosition


def video_neighbors(
    db: Session, course: Course, video: VideoPosition, window_s: float, limit: int
) -> list[RetrievedPassage]:
    """Videonun durdurulan ana yakın parçaları: 'bu adım' soruları için yumuşak öncelik girdisi.

    Yalnızca aynı dersin ve aynı videonun (`document_id`) zaman aralığı
    [time_s - window_s, time_s + window_s] ile örtüşen parçaları döner; başka videonun aynı
    saniyesi karışmaz. Sıra, parçanın orta noktasının `time_s`e uzaklığıdır (yakın önce).
    """
    midpoint = (Chunk.t_start + Chunk.t_end) / 2
    rows = db.execute(
        select(Chunk, Document.title)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.document_id == video.document_id,
            Chunk.course_id == course.id,
            Document.course_id == course.id,
            Document.status == "ready",
            Chunk.t_start.is_not(None),
            Chunk.t_end.is_not(None),
            Chunk.t_start <= video.time_s + window_s,
            Chunk.t_end >= video.time_s - window_s,
        )
        .order_by(func.abs(midpoint - video.time_s), Chunk.id)
        .limit(limit)
    )
    return [
        RetrievedPassage(
            source_id=str(chunk.id),
            document_id=chunk.document_id,
            document_title=title,
            text=chunk.text,
            score=0.0,
            page=chunk.page,
            t_start=chunk.t_start,
            t_end=chunk.t_end,
        )
        for chunk, title in rows
    ]
