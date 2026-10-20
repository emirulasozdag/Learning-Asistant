from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course, Document
from app.retrieval.types import RetrievedPassage


def dense_search(
    db: Session, course: Course, query_vector: list[float], k: int, embedding_model: str
) -> list[RetrievedPassage]:
    """pgvector ile anlamsal arama (kosinüs), dersin içinde kesin (exact) en yakın k parça.

    Yalnızca soruyla aynı embedder'ın (`embedding_model`) ürettiği vektörler karşılaştırılır:
    başka bir modelin (ör. testlerin sahte embedder'ı) vektörleri aynı uzayda değildir.

    Mesafe ders filtresinden sonra tüm ders parçaları için hesaplanır (kesin sonuç). HNSW +
    filtre, küçük bir dersi büyük bir tabloda ararken aday kaybeder (indeks önce en yakın ~40
    parçayı alır, filtre sonra uygulanır; ölçüm: 20 000 + 60 parçada küçük ders için 0 sonuç).
    Ders başına parça sayısı binler düzeyinde kaldıkça kesin arama yeterince hızlı (20 000
    parçada ~70 ms).
    """
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
    # MATERIALIZED: mesafe tüm ders parçaları için hesaplanır, sıralama dışarıda yapılır;
    # planlayıcı HNSW indeksiyle (+ sonradan filtre) yaklaşık aramaya geçemez.
    candidates = (
        select(Chunk.id.label("chunk_id"), distance)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.course_id == course.id,
            Document.course_id == course.id,
            Document.approved_at.is_not(None),
            Document.status == "ready",
            Chunk.embedding.is_not(None),
            Chunk.embedding_model == embedding_model,
        )
        .cte("candidates")
        .prefix_with("MATERIALIZED")
    )
    rows = db.execute(
        select(Chunk, Document.title, candidates.c.distance)
        .join(candidates, candidates.c.chunk_id == Chunk.id)
        .join(Document, Document.id == Chunk.document_id)
        .order_by(candidates.c.distance, Chunk.id)
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
