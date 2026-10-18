from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Course
from app.embeddings.base import Embedder
from app.embeddings.provider import get_embedder
from app.retrieval.dense import dense_search
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.lexical import lexical_search
from app.retrieval.types import RetrievalResult

# Her yöntemden alınan aday sayısı; RRF sonrası ilk `k` tanesi kullanılır.
CANDIDATES_PER_METHOD = 10
# Takip sorusunda önceki soruyla birlikte yapılan aramanın ağırlığı (yeni soru = 1).
CONTEXT_WEIGHT = 0.5


def retrieve(
    db: Session,
    course: Course,
    query: str,
    video_time_s: float | None = None,
    k: int = 5,
    embedder: Embedder | None = None,
    context: str | None = None,
) -> RetrievalResult:
    """Hibrit arama: anlamsal (e5 + pgvector) ve kelime (PostgreSQL FTS) → RRF → ilk k.

    `context` (takip sorusunda önceki soru) verilirse soru bir de onunla birlikte aranır;
    "peki karmaşıklığı ne?" gibi eksik sorular anlaşılır, ama sıralamada yeni soru önde kalır.

    Alakasızlık kapısı: hiç kelime eşleşmesi yoksa ve en iyi anlamsal benzerlik
    `retrieval_min_similarity` altındaysa soru dersle ilgisiz sayılır.
    Sonraki adımlar: video-zaman önceliği (`video_time.py`) ve rerank (`rerank.py`).
    """
    embedder = embedder or get_embedder()
    rankings = _search(db, course, query, embedder)
    weights = [1.0, 1.0]
    if context:
        rankings += _search(db, course, f"{context}\n{query}", embedder)
        weights += [CONTEXT_WEIGHT, CONTEXT_WEIGHT]

    dense_scores = [p.dense_score for r in rankings for p in r if p.dense_score is not None]
    best_similarity = max(dense_scores, default=None)
    has_keyword_match = any(p.lexical_rank is not None for r in rankings for p in r)
    relevant = has_keyword_match or (
        best_similarity is not None and best_similarity >= settings.retrieval_min_similarity
    )
    return RetrievalResult(
        passages=reciprocal_rank_fusion(rankings, weights=weights)[:k],
        relevant=relevant,
        best_similarity=best_similarity,
    )


def _search(db: Session, course: Course, text: str, embedder: Embedder):
    return [
        dense_search(db, course, embedder.embed_query(text), CANDIDATES_PER_METHOD),
        lexical_search(db, course, text, CANDIDATES_PER_METHOD),
    ]
