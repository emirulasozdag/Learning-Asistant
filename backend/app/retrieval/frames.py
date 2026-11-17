"""Video karelerinin türetilmiş metninde arama ve karenin yakın bağlamı (#24, ADR-10).

Kareler `chunks`tan ayrı aranır: anlamsal (aynı embedder'ın vektörleri) ve kelime (PostgreSQL
FTS) sıralamaları RRF ile birleşir. Yalnızca okunmuş (`readable`, `partial`) kareler aranır;
dersin onaylı ve hazır video dokümanlarından. Sonuç cevaba kanıt olarak girmez (ADR-10, #26);
değerlendirme ve kaynak görüntüleyici içindir.

Bir karenin bağlamı: ekranda kaldığı aralıkta konuşulan transkript ve önceki/sonraki kare.
Slayt anlamı tek karede yoksa (ör. ilk karede tanımlanan kavram ikincide kullanılıyor) komşu
kareler birlikte okunur.
"""

from dataclasses import dataclass, field

from sqlalchemy import and_, select, text
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course, Document, VideoFrame
from app.db.text_search import ts_config
from app.embeddings.base import Embedder
from app.retrieval.fusion import RRF_K

SEARCHABLE = ("readable", "partial")

# Sorgunun kelimelerinden en az biri geçen kareler; sıralama ts_rank (kapak yoğunluğu).
_LEXICAL = text(
    """
    WITH q AS (
        SELECT CAST(replace(CAST(plainto_tsquery(CAST(:config AS regconfig), :query) AS text),
                            '&', '|') AS tsquery) AS any_word
    )
    SELECT f.id
    FROM video_frames f
    JOIN documents d ON d.id = f.document_id AND d.course_id = :course_id
        AND d.approved_at IS NOT NULL AND d.status = 'ready'
    CROSS JOIN q
    WHERE f.course_id = :course_id
      AND f.status IN ('readable', 'partial')
      AND q.any_word <> CAST('' AS tsquery)
      AND f.search_vector @@ q.any_word
    ORDER BY ts_rank(f.search_vector, q.any_word, 1) DESC, f.id
    LIMIT :k
    """
)


@dataclass
class FrameHit:
    """Arama sonucu bir kare ve bağlamı."""

    frame: VideoFrame
    document_title: str
    # RRF puanı (yüksek önce).
    score: float
    # Anlamsal benzerlik (kosinüs, 0–1); anlamsal aramada bulunmadıysa None.
    dense_score: float | None = None
    # Kelime aramasındaki sıra (1 = en iyi); kelime eşleşmesi yoksa None.
    lexical_rank: int | None = None
    # Karenin aralığında konuşulan transkript parçaları, zamana göre.
    transcript: list[Chunk] = field(default_factory=list)
    # Aynı videoda hemen önceki ve sonraki kare (varsa), zamana göre.
    neighbors: list[VideoFrame] = field(default_factory=list)


def frame_search(
    db: Session,
    course: Course,
    query: str,
    embedder: Embedder,
    k: int = 5,
    candidates: int = 20,
) -> list[FrameHit]:
    """Dersin karelerinde arama; en iyi `k` kare bağlamıyla (transkript, komşu kareler)."""
    dense = _dense_ranking(db, course, embedder.embed_query(query), embedder.identity, candidates)
    lexical = [
        row.id
        for row in db.execute(
            _LEXICAL,
            {
                "config": ts_config(course.language),
                "query": query,
                "course_id": course.id,
                "k": candidates,
            },
        )
    ]
    scores: dict[int, float] = {}
    for ranking in ([frame_id for frame_id, _ in dense], lexical):
        for rank, frame_id in enumerate(ranking, start=1):
            scores[frame_id] = scores.get(frame_id, 0.0) + 1.0 / (RRF_K + rank)
    best = sorted(scores, key=lambda frame_id: (-scores[frame_id], frame_id))[:k]
    if not best:
        return []
    similarity = dict(dense)
    lexical_rank = {frame_id: rank for rank, frame_id in enumerate(lexical, start=1)}
    rows = {
        frame.id: (frame, title)
        for frame, title in db.execute(
            select(VideoFrame, Document.title)
            .join(Document, Document.id == VideoFrame.document_id)
            .where(VideoFrame.id.in_(best))
        )
    }
    hits = []
    for frame_id in best:
        frame, title = rows[frame_id]
        hits.append(
            FrameHit(
                frame=frame,
                document_title=title,
                score=scores[frame_id],
                dense_score=similarity.get(frame_id),
                lexical_rank=lexical_rank.get(frame_id),
                transcript=transcript_during(db, frame),
                neighbors=neighbor_frames(db, frame),
            )
        )
    return hits


def frames_overlapping(
    db: Session, document_id: int, t_start: float, t_end: float
) -> list[VideoFrame]:
    """Videonun [t_start, t_end] aralığında ekranda olan kareleri, zamana göre.

    Yalnızca sınırda değen kare sayılmaz (önceki slaytın bittiği an bir sonrakinin başıdır);
    anlık bir aralık (t_start == t_end) o anda ekrandaki kareyi verir.
    """
    if t_end > t_start:
        overlap = and_(VideoFrame.t_start < t_end, VideoFrame.t_end > t_start)
    else:
        overlap = and_(VideoFrame.t_start <= t_start, VideoFrame.t_end > t_start)
    return list(
        db.scalars(
            select(VideoFrame)
            .where(VideoFrame.document_id == document_id, overlap)
            .order_by(VideoFrame.t_start, VideoFrame.ordinal)
        )
    )


def transcript_during(db: Session, frame: VideoFrame) -> list[Chunk]:
    """Karenin ekranda kaldığı aralıkla örtüşen transkript parçaları, zamana göre."""
    return list(
        db.scalars(
            select(Chunk)
            .where(
                Chunk.document_id == frame.document_id,
                Chunk.t_start.is_not(None),
                Chunk.t_end.is_not(None),
                Chunk.t_start < frame.t_end,
                Chunk.t_end > frame.t_start,
            )
            .order_by(Chunk.t_start, Chunk.ordinal)
        )
    )


def neighbor_frames(db: Session, frame: VideoFrame) -> list[VideoFrame]:
    """Aynı videoda karenin hemen öncesindeki ve sonrasındaki kare (varsa), zamana göre."""
    return list(
        db.scalars(
            select(VideoFrame)
            .where(
                VideoFrame.document_id == frame.document_id,
                VideoFrame.ordinal.in_([frame.ordinal - 1, frame.ordinal + 1]),
            )
            .order_by(VideoFrame.ordinal)
        )
    )


def _dense_ranking(
    db: Session, course: Course, query_vector: list[float], embedding_model: str, k: int
) -> list[tuple[int, float]]:
    """(kare kimliği, kosinüs benzerliği), yakın önce. Ders filtresinden sonra kesin arama
    (bkz. `dense.dense_search`: HNSW + filtre küçük derste aday kaybeder)."""
    distance = VideoFrame.embedding.cosine_distance(query_vector).label("distance")
    candidates = (
        select(VideoFrame.id.label("frame_id"), distance)
        .join(Document, Document.id == VideoFrame.document_id)
        .where(
            VideoFrame.course_id == course.id,
            Document.course_id == course.id,
            Document.approved_at.is_not(None),
            Document.status == "ready",
            VideoFrame.status.in_(SEARCHABLE),
            VideoFrame.embedding.is_not(None),
            VideoFrame.embedding_model == embedding_model,
        )
        .cte("frame_candidates")
        .prefix_with("MATERIALIZED")
    )
    rows = db.execute(
        select(candidates.c.frame_id, candidates.c.distance)
        .order_by(candidates.c.distance, candidates.c.frame_id)
        .limit(k)
    )
    return [(frame_id, 1.0 - float(dist)) for frame_id, dist in rows]
