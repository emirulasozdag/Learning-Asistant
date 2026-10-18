from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course, Document
from app.retrieval.types import RetrievedPassage


def dense_search(
    db: Session, course: Course, query_vector: list[float], k: int
) -> list[RetrievedPassage]:
    """pgvector ile anlamsal arama (kosinüs). Ders filtresi aynı sorguda uygulanır."""
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
    rows = db.execute(
        select(Chunk, Document.title, distance)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.course_id == course.id, Chunk.embedding.is_not(None))
        .order_by(distance, Chunk.id)
        .limit(k)
    )
    return [
        RetrievedPassage(
            source_id=str(chunk.id),
            document_id=chunk.document_id,
            document_title=title,
            text=chunk.text,
            score=1.0 - float(dist),
            page=chunk.page,
            t_start=chunk.t_start,
            t_end=chunk.t_end,
            dense_score=1.0 - float(dist),
        )
        for chunk, title, dist in rows
    ]
